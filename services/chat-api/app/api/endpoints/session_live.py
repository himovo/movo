"""Authenticated session-scoped SSE endpoint (session-sharing realtime, T2).

``GET /api/sessions/{session_id}/live``: the bearer header alone
authenticates (the shared end-user dependency raises 401 for a missing or
invalid token), the shared ``SessionReadAuthorizer`` authorizes the initial
request (the existence-avoiding 404 for a non-member, cross-tenant probe,
or missing session) and every poll through the service, and the fixed SSE
headers and LF-only framing come from the plan's fixed protocol rules. On
mid-stream authorization loss the endpoint emits at most one terminal
``session.access.revoked`` frame and closes — the durable soft-removal is
identical for leave and removal (one ``update_one`` setting
``removed_at``), so the reason reports the removal member. No broadcaster,
no Redis, no WebSocket, no new collection: per-connection polling over
durable state only; client disconnect cancels the generator without a
database write or background broadcast.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse

from app.api.principal import ApiPrincipal, require_end_user_principal
from app.core.db import get_db
from app.dsh_runtime.bindings.repository import KernelBindingRepository
from app.dsh_runtime.conversation.participants_repository import (
    SessionParticipantsRepository,
)
from app.dsh_runtime.conversation.repository import ConversationRepository
from app.dsh_runtime.events.repository import KernelEventRepository
from app.dsh_runtime.session_access import (
    SessionReadAuthorizer,
    SessionReadDeniedError,
    SessionReadUnauthenticatedError,
)
from app.dsh_runtime.session_live import SessionLiveService, access_revoked_frame

# Poll cadence: a torn poll emits no data frame and "the next poll (one
# second later) recomputes" (plan Scope, fixed protocol rules). The
# heartbeat comment is emitted at most once per heartbeat interval
# (Settings.SESSION_LIVE_HEARTBEAT_SECONDS).
POLL_INTERVAL_SECONDS = 1.0

router = APIRouter(dependencies=[Depends(require_end_user_principal)])


@router.get("/sessions/{session_id}/live")
async def stream_session_live(
    session_id: str,
    principal: ApiPrincipal = Depends(require_end_user_principal),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    after: str | None = None,
) -> StreamingResponse:
    db = get_db()
    authorizer = SessionReadAuthorizer(db)
    try:
        await authorizer.authorize_read(
            session_id, tenant_id=principal.main_id, user_id=principal.user_id
        )
    except SessionReadUnauthenticatedError as exc:
        raise HTTPException(status_code=401, detail="invalid_token") from exc
    except SessionReadDeniedError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "session_not_found", "message": "Session not found"},
        ) from exc
    service = SessionLiveService(
        conversations=ConversationRepository(db),
        participants=SessionParticipantsRepository(db),
        events=KernelEventRepository(db),
        bindings=KernelBindingRepository(db),
        authorizer=authorizer,
    )
    tenant_id = principal.main_id
    user_id = principal.user_id

    async def live_events() -> AsyncIterator[str]:
        # Position state: the request's classification runs exactly once on
        # the first poll (Last-Event-ID wins when both are present); each
        # coherent data poll's cursor then threads forward as the next
        # poll's ``after`` resume position and the Last-Event-ID is dropped.
        resume_last_event_id = last_event_id
        resume_after = after
        known_fingerprint: str | None = None
        last_emitted = time.monotonic()
        while True:
            try:
                result = await service.poll(
                    session_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    last_event_id=resume_last_event_id,
                    after=resume_after,
                    known_member_fingerprint=known_fingerprint,
                )
            except SessionReadDeniedError:
                # Mid-stream access loss: at most one terminal frame, then
                # close. The durable soft-removal is identical for leave and
                # removal, so the reason reports the removal member.
                yield access_revoked_frame(session_id, "participant_removed").render()
                return
            if result.kind == "control":
                # Sole-frame control response: one no-ID frame, then the
                # response ends; the client performs the authoritative GET
                # and reopens with after=<live_cursor>.
                yield result.frames[0].render()
                return
            if result.frames:
                for frame in result.frames:
                    yield frame.render()
                last_emitted = time.monotonic()
            elif time.monotonic() - last_emitted >= service.heartbeat_seconds:
                # At most once per heartbeat interval; proves liveness
                # through the proxy instead of looking silently dead.
                yield result.heartbeat_comment
                last_emitted = time.monotonic()
            if result.kind == "data":
                # Only a coherent result updates the known fingerprint; a
                # torn poll's read is untrustworthy by definition.
                known_fingerprint = result.member_fingerprint
            if result.cursor is not None:
                # Only a data result advances the position; a torn poll
                # (cursor=None) retries the same request on the next poll.
                resume_last_event_id = None
                resume_after = result.cursor
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    return StreamingResponse(
        live_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
