from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.enterprise_capabilities.browser.engine.auth_suspension import browser_auth_suspensions
from app.api.endpoints.auth import _resolve_session_user
from app.governance.suspensions import SuspensionStatus, SuspensionType, suspension_service

router = APIRouter()


class BrowserAuthManualResumeRequest(BaseModel):
    user_id: str
    session_id: str


class TaskResumeRequest(BaseModel):
    suspension_id: str
    node_id: str = ""
    messages: list[dict] = Field(default_factory=list)
    model_id: str = ""
    signal: dict = Field(default_factory=dict)


class TaskSuspensionReadyRequest(BaseModel):
    signal: dict = Field(default_factory=dict)


async def _browser_auth_user_id(authorization: str | None, requested_user_id: str) -> str:
    resolved = await _resolve_session_user(authorization)
    authenticated_user_id = str(resolved["user"].get("_id") or "")
    if authenticated_user_id != str(requested_user_id or ""):
        raise HTTPException(status_code=403, detail="browser_auth_user_mismatch")
    return authenticated_user_id


@router.get("/tasks/browser-auth/status")
async def browser_auth_status(
    user_id: str,
    session_id: str,
    authorization: str | None = Header(default=None),
):
    authenticated_user_id = await _browser_auth_user_id(authorization, user_id)
    record = await browser_auth_suspensions.latest_for_session(
        user_id=authenticated_user_id,
        chat_session_id=str(session_id or ""),
    )
    return {"code": 0, "message": "success", "data": record.model_dump(mode="json") if record else None}


@router.post("/tasks/browser-auth/manual-ready")
async def browser_auth_manual_ready(
    payload: BrowserAuthManualResumeRequest,
    authorization: str | None = Header(default=None),
):
    authenticated_user_id = await _browser_auth_user_id(authorization, payload.user_id)
    record = await browser_auth_suspensions.latest_for_session(
        user_id=authenticated_user_id,
        chat_session_id=payload.session_id,
    )
    if record and record.status == "waiting_human":
        record = await browser_auth_suspensions.mark_ready(
            user_id=record.user_id,
            run_id=record.run_id,
            node_id=record.node_id,
            browser_session_id=record.browser_session_id,
            tab_id=record.tab_id,
            url=record.url,
            source="manual_return_to_agent",
        )
    return {"code": 0, "message": "success", "data": record.model_dump(mode="json") if record else None}


@router.get("/tasks/{run_id}/suspensions/active")
async def active_task_suspension(
    run_id: str,
    authorization: str | None = Header(default=None),
):
    resolved = await _resolve_session_user(authorization)
    user_id = str(resolved["user"].get("_id") or "")
    active = await suspension_service.store.latest_active_for_run(user_id=user_id, run_id=run_id)
    if active is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    return {"code": 0, "message": "success", "data": active.model_dump(mode="json") if active else None}


@router.post("/tasks/suspensions/{suspension_id}/manual-ready")
async def mark_task_suspension_manual_ready(
    suspension_id: str,
    payload: TaskSuspensionReadyRequest,
    authorization: str | None = Header(default=None),
):
    resolved = await _resolve_session_user(authorization)
    user_id = str(resolved["user"].get("_id") or "")
    record = await suspension_service.store.get(suspension_id)
    if not record or record.user_id != user_id:
        raise HTTPException(status_code=404, detail="suspension_not_found")
    context = dict(record.context or {})
    if (
        record.suspension_type != SuspensionType.USER_INPUT.value
        or not str(context.get("browser_session_id") or "").strip()
    ):
        raise HTTPException(status_code=409, detail="browser_intervention_required")
    if record.status == SuspensionStatus.SUSPENDED:
        signal = {
            **dict(payload.signal or {}),
            "type": "human_intervention_completed",
            "source": "manual_return_to_agent",
        }
        record = await suspension_service.mark_ready(
            suspension_id=record.suspension_id,
            user_id=user_id,
            signal=signal,
        )
    if not record or record.status != SuspensionStatus.READY:
        raise HTTPException(status_code=409, detail="suspension_not_ready")
    return {"code": 0, "message": "success", "data": record.model_dump(mode="json")}


@router.post("/tasks/{run_id}/resume")
async def resume_task(
    run_id: str,
    payload: TaskResumeRequest,
    authorization: str | None = Header(default=None),
):
    resolved = await _resolve_session_user(authorization)
    user_id = str(resolved["user"].get("_id") or "")
    suspension = await suspension_service.claim_resume(
        suspension_id=payload.suspension_id,
        user_id=user_id,
        resume_token=str((payload.signal or {}).get("resume_token") or ""),
    )
    if not suspension or suspension.run_id != run_id:
        raise HTTPException(status_code=409, detail="suspension_not_ready")
    if payload.node_id and payload.node_id != suspension.node_id:
        await suspension_service.release_resume(
            suspension_id=suspension.suspension_id,
            user_id=user_id,
            error="resume_node_mismatch",
        )
        raise HTTPException(status_code=409, detail="resume_node_mismatch")

    from app.api.endpoints.dsh_chat import ChatRequest, _start_chat_completions
    from app.dsh_runtime.application import dsh_runtime_application
    from app.enterprise_capabilities.browser.resume_lifecycle import schedule_browser_resume
    from app.enterprise_capabilities.browser.engine.intervention_suspension import bind_browser_resume_signal

    # DSH owns the existing Session history. Never replay client-supplied
    # history into the resumed turn; only send a bounded continuation command.
    resume_signal = bind_browser_resume_signal(
        suspension,
        dict(payload.signal or suspension.ready_signal or {}),
    )
    mission = dict((suspension.context or {}).get("mission") or {})
    resume_language = "en" if str(mission.get("language") or "").lower().startswith("en") else "zh"
    resume_messages = [{
        "role": "user",
        "content": (
            "Continue the browser task that was paused for human assistance."
            if resume_language == "en"
            else "继续刚才暂停的浏览器任务。"
        ),
    }]
    request = ChatRequest.model_validate({
        "messages": resume_messages,
        "modelId": payload.model_id or None,
        "output_spec": {
            "task_id": suspension.task_id,
            "session_id": suspension.task_id,
            "language": resume_language,
        },
    })
    try:
        response = await _start_chat_completions(
            request,
            authorization,
            trusted_turn_context={"browser_resume": {
                "run_id": suspension.run_id,
                "node_id": suspension.node_id,
                "suspension_id": suspension.suspension_id,
                "browser_session_id": str((suspension.context or {}).get("browser_session_id") or suspension.task_id),
                "mission": mission,
                "resume_signal": resume_signal,
            }},
        )
    except Exception as exc:
        await suspension_service.release_resume(
            suspension_id=suspension.suspension_id,
            user_id=user_id,
            error=str(exc),
        )
        raise

    message_id = str(response.headers.get("X-Message-Id") or "")
    if not message_id:
        await suspension_service.release_resume(
            suspension_id=suspension.suspension_id,
            user_id=user_id,
            error="resume_dsh_turn_missing",
        )
        raise HTTPException(status_code=503, detail="resume_dsh_turn_missing")
    schedule_browser_resume(
        chat_service=dsh_runtime_application.require_chat(),
        message_id=message_id,
        suspension_id=suspension.suspension_id,
        user_id=user_id,
    )

    async def _resume_stream():
        async for chunk in response.body_iterator:
            yield chunk

    headers = {
        key: value for key, value in dict(response.headers).items()
        if key.lower() not in {"content-length", "content-type"}
    }
    return StreamingResponse(
        _resume_stream(),
        status_code=response.status_code,
        media_type="text/event-stream",
        headers=headers,
    )
