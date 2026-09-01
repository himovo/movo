"""Authenticated DSH Tool Gateway plus end-user approval control surface."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Header, HTTPException, Query, Request

from app.api.endpoints.auth import _resolve_session_user
from app.core.config import get_settings
from app.core.tenant import resolve_main_id
from app.dsh_runtime.application import dsh_runtime_application
from app.dsh_runtime.tool_gateway import ToolGatewayTokenService
from app.enterprise_capabilities.tools import ApprovalAskRequest, ApprovalDecisionRequest, ToolExecuteRequest
from app.enterprise_capabilities.tools.service import ToolPolicyDenied
from app.enterprise_capabilities.tools.result_projection import canonical_tool_result


internal_router = APIRouter(prefix="/internal/dsh/tools", tags=["dsh-internal"])
public_router = APIRouter(prefix="/dsh/tool-approvals", tags=["dsh-tool-approvals"])


def _tokens() -> ToolGatewayTokenService:
    settings = get_settings()
    return ToolGatewayTokenService(str(settings.DSH_MODEL_GATEWAY_SIGNING_SECRET or settings.ASKAI_ADMIN_JWT_SECRET or ""))


def _claims(authorization: str):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing Tool Gateway bearer token")
    try:
        return _tokens().verify(authorization.removeprefix("Bearer ").strip())
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@internal_router.post("/approval/request")
async def request_approval(
    payload: ApprovalAskRequest,
    request: Request,
    authorization: str = Header(default=""),
):
    try:
        approval = asyncio.create_task(
            dsh_runtime_application.require_tools().request_approval(payload, _claims(authorization))
        )
        disconnect = asyncio.create_task(_wait_for_disconnect(request))
        done, _ = await asyncio.wait({approval, disconnect}, return_when=asyncio.FIRST_COMPLETED)
        if disconnect in done and not approval.done():
            approval.cancel()
            try:
                await approval
            except asyncio.CancelledError:
                pass
            raise HTTPException(status_code=499, detail="DSH approval caller disconnected")
        disconnect.cancel()
        outcome = await approval
        return {"outcome": outcome}
    except ToolPolicyDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@internal_router.post("/execute")
async def execute(payload: ToolExecuteRequest, request: Request, authorization: str = Header(default="")):
    try:
        execution = asyncio.create_task(
            dsh_runtime_application.require_tools().execute(payload, _claims(authorization))
        )
        disconnect = asyncio.create_task(_wait_for_disconnect(request))
        done, _ = await asyncio.wait({execution, disconnect}, return_when=asyncio.FIRST_COMPLETED)
        if disconnect in done and not execution.done():
            execution.cancel()
            try:
                await execution
            except asyncio.CancelledError:
                pass
            raise HTTPException(status_code=499, detail="DSH tool caller disconnected")
        disconnect.cancel()
        receipt = await execution
        if receipt.status == "succeeded":
            canonical = canonical_tool_result(receipt.result)
            return {"ok": True, "receipt": receipt.model_dump(mode="json"), "result": canonical}
        raise HTTPException(
            status_code=408 if receipt.status == "timed_out" else 502,
            detail={"code": f"tool_{receipt.status}", "message": receipt.error, "receipt": receipt.model_dump(mode="json")},
        )
    except ToolPolicyDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


async def _wait_for_disconnect(request: Request) -> None:
    while not await request.is_disconnected():
        await asyncio.sleep(0.05)


async def _identity(authorization: str | None) -> tuple[str, str]:
    resolved = await _resolve_session_user(authorization)
    return resolve_main_id(resolved["main_id"]), str(resolved["user"].get("_id") or "")


@public_router.get("")
async def pending_approvals(
    conversation_id: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
):
    tenant_id, user_id = await _identity(authorization)
    rows = await dsh_runtime_application.require_tools().list_pending(
        tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
    )
    return {"code": 0, "data": [row.model_dump(mode="json") for row in rows]}


@public_router.post("/{action_id}/decision")
async def decide_approval(
    action_id: str,
    payload: ApprovalDecisionRequest,
    authorization: str | None = Header(default=None),
):
    tenant_id, user_id = await _identity(authorization)
    try:
        row = await dsh_runtime_application.require_tools().decide(
            action_id,
            decision=payload.decision,
            actor_id=user_id,
            tenant_id=tenant_id,
            subject_user_id=user_id,
            grant_scope=payload.grantScope,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="approval_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ToolPolicyDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"code": 0, "data": row.model_dump(mode="json")}
