"""Formal Chat API backed exclusively by the DSH runtime application."""

from __future__ import annotations

import os
from typing import Any, Literal

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.endpoints.auth import _resolve_session_user
from app.core.config import get_settings
from app.core.quota_policy import QuotaExceededError, assert_quota_available
from app.core.tenant import resolve_main_id
from app.dsh_runtime.application import dsh_runtime_application
from app.dsh_runtime.chat_service import ConversationBusyError
from app.dsh_runtime.errors import DshRuntimeError
from app.utils.oss_uploader import AliyunOSSUploader
from app.utils.uploads import read_upload_with_limit
from app.dsh_runtime.desktop_binding import DesktopSessionIdentity
from app.dsh_runtime.turn_admission import admit_skill_selection
from app.governance.position_policy import MongoEmployeePolicyResolver
from app.governance.audit import record_position_policy_event


router = APIRouter(tags=["dsh-chat"])


async def _require_code_capability(tenant_id: str, user_id: str) -> None:
    policy = await MongoEmployeePolicyResolver().resolve(tenant_id, user_id)
    if not policy.allows_capability("code_generation"):
        await record_position_policy_event(
            tenant_id=tenant_id, user_id=user_id, action="capability.denied", target="code_generation",
        )
        raise HTTPException(
            status_code=403,
            detail={"code": "position_role_denied", "message": "当前岗位未开通代码生成能力，本次任务未执行"},
        )


class Attachment(BaseModel):
    object_path: str | None = None
    url: str | None = None
    signed_url: str | None = None
    filename: str | None = None
    content_type: str | None = None
    size: int | None = None


class Message(BaseModel):
    role: str
    content: str
    images: list[Attachment] | None = None
    documents: list[Attachment] | None = None


class ChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    messages: list[Message]
    model: str | None = None
    model_id: str | None = Field(default=None, alias="modelId")
    output_spec: dict[str, Any] | None = None
    upstream_context: dict[str, Any] | None = None
    knowledge_qa_enabled: bool = Field(
        default=False,
        alias="knowledgeQaEnabled",
        description="Strict internal-knowledge-only mode. False keeps DSH automatic retrieval enabled.",
    )
    knowledge_base_ids: list[str] | None = Field(default=None, alias="knowledgeBaseIds")
    timezone: str | None = Field(default=None, min_length=1, max_length=100)


class CancelRequest(BaseModel):
    session_id: str


class DesktopRuntimeProfileRequest(BaseModel):
    model_id: str | None = Field(default=None, alias="modelId")


class DesktopSessionCommitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str = Field(min_length=1, max_length=256)
    kernel_session_id: str = Field(min_length=1, max_length=256)
    dsh_workspace_id: str = Field(min_length=1, max_length=256)
    profile_version: str = Field(min_length=1, max_length=256)
    model_instance_id: str = Field(min_length=1, max_length=256)
    device_id: str = Field(min_length=1, max_length=256)
    source_workspace_id: str = Field(min_length=1, max_length=256)
    git_branch: str | None = Field(default=None, max_length=256)
    source_ref: str | None = Field(default=None, max_length=512)
    base_commit: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{40,64}$")
    detached_head: bool = False
    execution_mode: Literal["local", "worktree"] = "local"
    worktree: bool = False
    title: str = Field(default="Code task", max_length=500)


class DesktopTurnStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_id: str = Field(min_length=1, max_length=256)
    message_id: str = Field(min_length=1, max_length=256)
    text: str = Field(min_length=1, max_length=2_000_000)


class DesktopGitStateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_id: str = Field(min_length=1, max_length=256)
    git_branch: str = Field(min_length=1, max_length=256)
    head_commit: str = Field(pattern=r"^[0-9a-fA-F]{40,64}$")


class DesktopTurnEventsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_id: str = Field(min_length=1, max_length=256)
    message_id: str = Field(min_length=1, max_length=256)
    events: list[dict[str, Any]] = Field(max_length=500)


class DesktopRuntimeRebindRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_id: str = Field(min_length=1, max_length=256)
    runtime_id: str = Field(min_length=1, max_length=256)
    profile_version: str = Field(min_length=1, max_length=256)


class ApiResponse(BaseModel):
    code: int = 0
    message: str | None = None
    data: object | None = None


def _latest_user(request: ChatRequest) -> Message:
    for message in reversed(request.messages):
        if message.role.strip().lower() == "user":
            return message
    raise HTTPException(status_code=400, detail="A user message is required")


async def _identity(authorization: str | None) -> tuple[str, str, dict[str, Any]]:
    resolved = await _resolve_session_user(authorization if isinstance(authorization, str) else None)
    user = resolved["user"]
    return resolve_main_id(resolved["main_id"]), str(user.get("_id") or ""), user


@router.post("/chat/completions")
async def chat_completions(
    request: ChatRequest,
    authorization: str | None = Header(default=None),
):
    return await _start_chat_completions(request, authorization)


async def _start_chat_completions(
    request: ChatRequest,
    authorization: str | None,
    *,
    trusted_turn_context: dict[str, Any] | None = None,
):
    """Internal start helper; trusted context is never part of ChatRequest."""
    tenant_id, user_id, user = await _identity(authorization)
    try:
        await assert_quota_available(tenant_id, user)
    except QuotaExceededError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    latest = _latest_user(request)
    text = latest.content.strip()
    if not text:
        raise HTTPException(status_code=400, detail="A non-empty text message is required")
    output_spec = dict(request.output_spec or {})
    selected_skill_id = str(output_spec.get("selected_skill_id") or output_spec.get("selectedSkillId") or "").strip()
    try:
        skill_selection = await admit_skill_selection(
            tenant_id=tenant_id,
            user_id=user_id,
            selected_skill_id=selected_skill_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    conversation_id = str(output_spec.get("task_id") or output_spec.get("session_id") or "").strip() or None
    try:
        turn = await dsh_runtime_application.require_chat().prepare_turn(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            text=text,
            model_instance_id=str(request.model_id or output_spec.get("model_id") or "").strip() or None,
            timezone_name=request.timezone,
            images=[item.model_dump(mode="json") for item in list(latest.images or [])],
            documents=[item.model_dump(mode="json") for item in list(latest.documents or [])],
            knowledge_qa_enabled=request.knowledge_qa_enabled,
            knowledge_base_ids=request.knowledge_base_ids,
            trusted_turn_context=trusted_turn_context,
            language_name=str(output_spec.get("language") or output_spec.get("locale") or "") or None,
            selected_writing_skill_id=skill_selection.selected_writing_skill_id,
            selected_skill_id=skill_selection.selected_skill_id,
        )
    except ConversationBusyError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "session_already_running", "message": str(exc), "session_id": conversation_id},
        ) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DshRuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "dsh_runtime_unavailable", "message": str(exc), "retryable": True},
        ) from exc
    return StreamingResponse(
        dsh_runtime_application.require_chat().stream(turn, tenant_id=tenant_id, user_id=user_id),
        media_type="text/event-stream",
        headers={
            "X-Session-Id": turn.conversation_id,
            "X-Message-Id": turn.message_id,
            "X-Execution-Protocol": "3",
            "X-Agent-Kernel": "dsh",
        },
    )


@router.post("/chat")
async def chat_entry(
    request: ChatRequest,
    authorization: str | None = Header(default=None),
):
    return await chat_completions(request, authorization)


@router.post("/desktop/dsh/runtime-profile", response_model=ApiResponse)
async def desktop_runtime_profile(
    payload: DesktopRuntimeProfileRequest,
    authorization: str | None = Header(default=None),
) -> ApiResponse:
    """Issue an authenticated, short-lived Runtime Profile for Electron main only."""
    tenant_id, user_id, user = await _identity(authorization)
    await _require_code_capability(tenant_id, user_id)
    await record_position_policy_event(
        tenant_id=tenant_id, user_id=user_id, action="capability.used", target="code_generation",
    )
    try:
        await assert_quota_available(tenant_id, user)
        prepared = await dsh_runtime_application.require_desktop_bootstrap().prepare(
            tenant_id=tenant_id,
            user_id=user_id,
            model_instance_id=str(payload.model_id or "").strip() or None,
        )
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApiResponse(code=0, message="ok", data={
        "profile_version": prepared.profile_version,
        "model_instance_id": prepared.model_instance_id,
        "model_profile": prepared.model_profile,
    })


@router.post("/desktop/dsh/capability-check", response_model=ApiResponse)
async def desktop_code_capability_check(
    authorization: str | None = Header(default=None),
) -> ApiResponse:
    tenant_id, user_id, _ = await _identity(authorization)
    await _require_code_capability(tenant_id, user_id)
    return ApiResponse(code=0, message="ok", data={"allowed": True})


@router.post("/desktop/dsh/sessions/commit", response_model=ApiResponse)
async def desktop_session_commit(
    payload: DesktopSessionCommitRequest,
    authorization: str | None = Header(default=None),
) -> ApiResponse:
    tenant_id, user_id, _ = await _identity(authorization)
    await _require_code_capability(tenant_id, user_id)
    try:
        binding = await dsh_runtime_application.require_desktop_bindings().commit(
            tenant_id=tenant_id,
            user_id=user_id,
            identity=DesktopSessionIdentity(
                runtime_id=payload.runtime_id,
                kernel_session_id=payload.kernel_session_id,
                dsh_workspace_id=payload.dsh_workspace_id,
                profile_version=payload.profile_version,
                model_instance_id=payload.model_instance_id,
                device_id=payload.device_id,
                source_workspace_id=payload.source_workspace_id,
                git_branch=payload.git_branch,
                source_ref=payload.source_ref,
                base_commit=payload.base_commit,
                detached_head=payload.detached_head,
                execution_mode=payload.execution_mode,
                worktree=payload.worktree,
            ),
            title=payload.title,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ApiResponse(code=0, message="ok", data={
        "conversation_id": str(binding["conversation_id"]),
        "binding_id": str(binding["binding_id"]),
        "execution_location": "desktop",
        "preset_id": "code",
    })


@router.post("/desktop/dsh/sessions/{kernel_session_id}/git-state", response_model=ApiResponse)
async def desktop_git_state(
    kernel_session_id: str,
    payload: DesktopGitStateRequest,
    authorization: str | None = Header(default=None),
) -> ApiResponse:
    tenant_id, user_id, _ = await _identity(authorization)
    try:
        await dsh_runtime_application.require_desktop_bindings().update_git_state(
            tenant_id=tenant_id,
            user_id=user_id,
            device_id=payload.device_id,
            kernel_session_id=kernel_session_id,
            git_branch=payload.git_branch,
            head_commit=payload.head_commit,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ApiResponse(code=0, message="ok", data={"updated": True})


@router.post("/desktop/dsh/sessions/{kernel_session_id}/turns/start", response_model=ApiResponse)
async def desktop_turn_start(
    kernel_session_id: str,
    payload: DesktopTurnStartRequest,
    authorization: str | None = Header(default=None),
) -> ApiResponse:
    tenant_id, user_id, _ = await _identity(authorization)
    await _require_code_capability(tenant_id, user_id)
    try:
        data = await dsh_runtime_application.require_desktop_bindings().start_turn(
            tenant_id=tenant_id, user_id=user_id, device_id=payload.device_id,
            kernel_session_id=kernel_session_id, text=payload.text,
            message_id=payload.message_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ApiResponse(code=0, message="ok", data=data)


@router.get("/desktop/dsh/conversations/{conversation_id}/binding", response_model=ApiResponse)
async def desktop_conversation_binding(
    conversation_id: str,
    device_id: str,
    authorization: str | None = Header(default=None),
) -> ApiResponse:
    tenant_id, user_id, _ = await _identity(authorization)
    try:
        binding = await dsh_runtime_application.require_desktop_bindings().resolve(
            tenant_id=tenant_id, user_id=user_id, device_id=device_id,
            conversation_id=conversation_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if binding is None:
        return ApiResponse(code=0, message="ok", data=None)
    return ApiResponse(code=0, message="ok", data={
        "runtime_id": str(binding["runtime_id"]),
        "kernel_session_id": str(binding["kernel_session_id"]),
        "dsh_workspace_id": str(binding["dsh_workspace_id"]),
        "preset_id": "code",
        "profile_version": str(binding["profile_version"]),
        "model_instance_id": str(binding["model_instance_id"]),
        "conversation_id": str(binding["conversation_id"]),
        "binding_id": str(binding["binding_id"]),
        "source_workspace_id": str(binding.get("source_workspace_id") or ""),
        "git_branch": binding.get("git_branch"),
        "base_commit": binding.get("base_commit"),
        "worktree": bool(binding.get("worktree")),
    })


@router.post("/desktop/dsh/conversations/{conversation_id}/runtime", response_model=ApiResponse)
async def desktop_conversation_runtime_rebind(
    conversation_id: str,
    payload: DesktopRuntimeRebindRequest,
    authorization: str | None = Header(default=None),
) -> ApiResponse:
    tenant_id, user_id, _ = await _identity(authorization)
    try:
        await dsh_runtime_application.require_desktop_bindings().rebind_runtime(
            tenant_id=tenant_id, user_id=user_id, device_id=payload.device_id,
            conversation_id=conversation_id, profile_version=payload.profile_version,
            runtime_id=payload.runtime_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ApiResponse(code=0, message="ok", data={"runtime_id": payload.runtime_id})


@router.post("/desktop/dsh/sessions/{kernel_session_id}/turns/events", response_model=ApiResponse)
async def desktop_turn_events(
    kernel_session_id: str,
    payload: DesktopTurnEventsRequest,
    authorization: str | None = Header(default=None),
) -> ApiResponse:
    tenant_id, user_id, _ = await _identity(authorization)
    await _require_code_capability(tenant_id, user_id)
    try:
        data = await dsh_runtime_application.require_desktop_bindings().project_events(
            tenant_id=tenant_id, user_id=user_id, device_id=payload.device_id,
            kernel_session_id=kernel_session_id, message_id=payload.message_id,
            events=payload.events,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ApiResponse(code=0, message="ok", data=data)


@router.get("/chat/messages/{message_id}/events", response_model=ApiResponse)
async def chat_message_events(
    message_id: str,
    after: int = 0,
    after_cursor: int | None = None,
    authorization: str | None = Header(default=None),
) -> ApiResponse:
    tenant_id, user_id, _ = await _identity(authorization)
    cursor = max(0, int(after if after_cursor is None else after_cursor))
    try:
        data = await dsh_runtime_application.require_chat().snapshot(
            message_id,
            tenant_id=tenant_id,
            user_id=user_id,
            after_cursor=cursor,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="message_not_found") from exc
    return ApiResponse(code=0, message="ok", data=data)


@router.post("/chat/cancel", response_model=ApiResponse)
async def chat_cancel(
    payload: CancelRequest,
    authorization: str | None = Header(default=None),
) -> ApiResponse:
    tenant_id, user_id, _ = await _identity(authorization)
    try:
        await dsh_runtime_application.require_tools().cancel_conversation(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=payload.session_id,
        )
        cancelled = await dsh_runtime_application.require_chat().cancel(
            payload.session_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="session_not_found") from exc
    except DshRuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "dsh_cancel_pending", "message": str(exc), "retryable": True},
        ) from exc
    return ApiResponse(code=0 if cancelled else 404, message="ok" if cancelled else "session_not_found")


@router.post("/chat/upload-image", response_model=ApiResponse)
async def upload_chat_image(
    user_id: str = Form(default=""),
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
) -> ApiResponse:
    _, authenticated_user_id, _ = await _identity(authorization)
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image uploads are supported")
    settings = get_settings()
    content = await read_upload_with_limit(file, max_bytes=settings.MAX_UPLOAD_IMAGE_BYTES, label="Image upload")
    uploader = AliyunOSSUploader()
    url, object_path = uploader.upload_bytes_with_path(
        content,
        user_id=authenticated_user_id,
        file_name=file.filename or "chat_image.bin",
        content_type=file.content_type,
    )
    return ApiResponse(code=0, message="success", data={
        "object_path": object_path,
        "url": url,
        "signed_url": uploader.sign_url(object_path),
        "filename": file.filename,
        "content_type": file.content_type,
        "size": len(content),
    })


@router.post("/chat/upload-document", response_model=ApiResponse)
async def upload_chat_document(
    user_id: str = Form(default=""),
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
) -> ApiResponse:
    _, authenticated_user_id, _ = await _identity(authorization)
    filename = str(file.filename or "chat_document.bin").strip() or "chat_document.bin"
    ext = os.path.splitext(filename)[1].lower()
    allowed_exts = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".txt", ".md", ".xlsx", ".xlsm", ".csv", ".tsv", ".xls"}
    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail="Unsupported document type")
    settings = get_settings()
    content = await read_upload_with_limit(file, max_bytes=settings.MAX_UPLOAD_DOCUMENT_BYTES, label="Document upload")
    uploader = AliyunOSSUploader()
    url, object_path = uploader.upload_bytes_with_path(
        content,
        user_id=authenticated_user_id,
        file_name=filename,
        content_type=file.content_type,
    )
    return ApiResponse(code=0, message="success", data={
        "object_path": object_path,
        "url": url,
        "signed_url": uploader.sign_url(object_path),
        "filename": filename,
        "content_type": file.content_type,
        "size": len(content),
    })
