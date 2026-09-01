"""WebSocket endpoint used by the local browser agent to connect."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Dict

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketState

from .registry import agent_registry
from app.enterprise_capabilities.browser.engine.recording import human_recording_store
from app.enterprise_capabilities.browser.engine.workflow_cache.manual_capture import capture_manual_recording
from app.enterprise_capabilities.browser.engine.workflow_cache.manual_analysis import manual_recording_analyzer
from app.enterprise_capabilities.browser.engine.workflow_cache.service import browser_workflow_cache


router = APIRouter()


def _extract_user_id(ws: WebSocket) -> str | None:
    # Priority: explicit ?user_id= (from agent) > X-User-Id header > bearer
    # token. The bearer is used last because it's typically a session token,
    # not a user identifier — but we keep it as a dev-time fallback.
    uid = (ws.query_params.get("user_id") or "").strip()
    if uid:
        return uid
    hdr = (ws.headers.get("x-user-id") or "").strip()
    if hdr:
        return hdr
    auth = ws.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        tok = auth.split(" ", 1)[1].strip()
        if tok:
            return tok
    return None


@router.websocket("/agent/connect")
async def agent_connect(ws: WebSocket) -> None:
    await ws.accept()
    user_id = _extract_user_id(ws)
    if not user_id:
        await ws.close(code=1008)
        return

    async def send(frame: Dict[str, Any]) -> None:
        if ws.application_state == WebSocketState.CONNECTED:
            await ws.send_text(json.dumps(frame, ensure_ascii=False))

    conn = await agent_registry.attach(user_id=user_id, send=send, capabilities=[])

    async def ping_loop() -> None:
        while True:
            await asyncio.sleep(20)
            try:
                await send({"type": "ping"})
            except Exception:
                return

    pinger = asyncio.create_task(ping_loop())
    try:
        while True:
            raw = await ws.receive_text()
            try:
                frame = json.loads(raw)
            except Exception:
                continue
            if not isinstance(frame, dict):
                continue
            await agent_registry.on_frame(user_id, frame)
    except WebSocketDisconnect:
        pass
    finally:
        pinger.cancel()
        await agent_registry.detach(user_id, conn)


@router.post("/browser/show")
async def browser_show(body: dict):
    uid = str(body.get("user_id") or "")
    domain = str(body.get("domain") or "")
    url = str(body.get("url") or "")
    # purpose steers the agent's completion policy:
    #   "login"            → auto-detect via URL pattern and auto-close
    #   "user_interaction" → just open, wait for explicit hide_browser
    # Anything unknown is treated as user_interaction (safer default —
    # never auto-close on non-login flows; that's what caused the
    # "window flashes open-and-close" bug on ask_user interventions).
    purpose = str(body.get("purpose") or "user_interaction").strip() or "user_interaction"
    ok = await agent_registry.send_command(
        uid, "show_browser", domain=domain, url=url, purpose=purpose,
    )
    return {"ok": ok}


@router.post("/browser/hide")
async def browser_hide(body: dict):
    uid = str(body.get("user_id") or "")
    ok = await agent_registry.send_command(uid, "hide_browser")
    return {"ok": ok}


# -- Recording REST / SSE endpoints -----------------------------------------

class RecordingStart(BaseModel):
    user_id: str
    url: str = ""
    session_id: str = "default"
    operation: str = ""


@router.post("/browser/recording/start")
async def recording_start(body: RecordingStart):
    recording_id = f"manual_{uuid.uuid4().hex}"
    ok = await agent_registry.send_command(
        body.user_id,
        "recording_start",
        url=body.url,
        session_id=body.session_id or "default",
        recording_id=recording_id,
        recording_mode="manual",
        operation=body.operation,
    )
    return {"ok": ok, "recording_id": recording_id}


@router.post("/browser/recording/stop")
async def recording_stop(body: dict):
    uid = str(body.get("user_id") or "")
    ok = await agent_registry.send_command(
        uid,
        "recording_stop",
        session_id=str(body.get("session_id") or "default"),
        recording_id=str(body.get("recording_id") or ""),
    )
    return {"ok": ok}


class RecordingCacheRequest(BaseModel):
    user_id: str
    recording_id: str
    operation: str
    display_name: str = ""
    capability_id: str = ""
    main_id: str = "default"
    included_sequences: list[int] | None = None
    variable_names: Dict[int, str] = Field(default_factory=dict)


class RecordingAnalysisRequest(BaseModel):
    user_id: str
    recording_id: str


@router.post("/browser/recording/analyze")
async def recording_analyze(body: RecordingAnalysisRequest):
    stopped = await human_recording_store.wait_stopped(
        body.recording_id, timeout=15.0, user_id=body.user_id,
    )
    if not stopped:
        return {"ok": False, "reason": "recording_stop_timeout", "analysis": None}
    events = await human_recording_store.list(body.recording_id, user_id=body.user_id)
    analysis = await manual_recording_analyzer.analyze(events)
    return {"ok": True, "analysis": analysis.as_dict()}


@router.post("/browser/recording/cache")
async def recording_cache(body: RecordingCacheRequest):
    stopped = await human_recording_store.wait_stopped(
        body.recording_id, timeout=15.0, user_id=body.user_id,
    )
    if not stopped:
        return {"ok": False, "reason": "recording_stop_timeout"}
    events = await human_recording_store.list(body.recording_id, user_id=body.user_id)
    if body.included_sequences is not None:
        included = {int(item) for item in body.included_sequences}
        events = [
            item for item in events
            if str(item.get("type") or "") in {"recording_started", "recording_stopped"}
            or int(item.get("sequence") or 0) in included
        ]
    accepted, reason = await capture_manual_recording(
        cache=browser_workflow_cache,
        user_id=body.user_id,
        main_id=body.main_id,
        recording_id=body.recording_id,
        operation=body.operation,
        events=events,
        variable_names=body.variable_names,
        display_name=body.display_name,
        capability_id=body.capability_id,
    )
    if accepted:
        await human_recording_store.purge(body.recording_id, user_id=body.user_id)
    return {"ok": accepted, "reason": reason}


@router.get("/browser/recording/stream")
async def recording_stream(user_id: str = Query(...)):
    """SSE endpoint that streams recording_event payloads as NDJSON lines."""
    q = agent_registry.subscribe_recording(user_id)

    async def _gen():
        try:
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=30)
                except asyncio.TimeoutError:
                    yield "\n"
                    continue
                if ev is None:
                    break
                yield json.dumps(ev, ensure_ascii=False) + "\n"
        finally:
            agent_registry.unsubscribe_recording(user_id, q)

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
