"""Real-mongod direct-FastAPI coverage for the session SSE endpoint (T2).

QA-happy (plan row L106): the real ``GET /api/sessions/{id}/live`` endpoint
driven through ``httpx.ASGITransport`` (no gateway proxy) with the shared
bearer dependency and the shared ``SessionReadAuthorizer``: an owner and an
active participant open the stream, a durable message/event is advanced and
arrives as LF-only framed data, an idle stream heartbeats and closes cleanly
when cancelled, and the authorizer is exercised again after the membership
changes. The admission boundary is proven through the REAL
``DshChatService.prepare_turn``: a barrier removes the member between the
pre-claim recheck and the claim, and the post-claim recheck rolls the claim
back (no orphaned user message, no second assistant claim).

QA-failure (plan row L107): missing/malformed bearer (401), cross-tenant,
never-member and removed-member connects (existence-avoiding 404); a member
removed after connection receives at most one no-ID terminal access frame
and no later execution event; an in-flight send suppresses the data frame
when removal commits before the send lock, while a frame already written
before removal is the single frame permitted before the timer revokes.

Every assertion runs against a real mongod (the shared ``real_mongo_db``
harness); the endpoint's own module seams (``get_db``, poll interval) and
the auth secret are the only monkeypatches.
"""

# allow: SIZE_OK — the frozen plan pins BOTH T2 QA matrices (endpoint and
# admission boundary) to this single T2-owned path, mirroring T1's
# single-file pattern; splitting would break the plan's evidence mapping.

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from bson import ObjectId

import app.dsh_runtime.chat_service as chat_service_module
from app.core.config import get_settings
from app.core.end_user_auth import build_session_token
from app.dsh_runtime.bindings.repository import KernelBindingRepository
from app.dsh_runtime.chat_service import DshChatService
from app.dsh_runtime.conversation import ConversationRepository
from app.dsh_runtime.conversation.participants_repository import (
    SessionParticipantsRepository,
)
from app.dsh_runtime.events.repository import KernelEventRepository
from app.dsh_runtime.runtime_coordinator import RuntimeCoordinator
from app.dsh_runtime.session_access import SessionReadDeniedError
from app.dsh_runtime.session_live import EVENT_ACCESS_REVOKED

TENANT = "tenant-t02"
OTHER_TENANT = "tenant-t02-other"
SECRET = "t02-live-secret"
OWNER = "owner"
PARTICIPANT = "participant"

REVOKED_LINE = "session.access.revoked"

PROJECTIONS = KernelEventRepository.PROJECTIONS

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def live_env(real_mongo_db, monkeypatch):
    """The endpoint's real seams: auth secret, poll cadence, db binding."""
    harness = real_mongo_db
    monkeypatch.setenv("END_USER_AUTH_SECRET", SECRET)
    monkeypatch.setenv("SESSION_LIVE_HEARTBEAT_SECONDS", "0.05")
    get_settings.cache_clear()
    import app.api.endpoints.session_live as session_live_module
    import app.services.end_user_session as end_user_session_module

    monkeypatch.setattr(end_user_session_module, "get_db", lambda: harness.db)
    monkeypatch.setattr(session_live_module, "get_db", lambda: harness.db)
    monkeypatch.setattr(session_live_module, "POLL_INTERVAL_SECONDS", 0.01)
    try:
        yield harness
    finally:
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Seeding helpers (real repositories only)
# ---------------------------------------------------------------------------


def _seed_principal(harness, *, main_id: str = TENANT) -> tuple[str, str]:
    """Insert an active end user plus an active session token."""
    user_oid = ObjectId()
    token_id = f"tok-{uuid.uuid4().hex}"
    now = datetime.utcnow()
    harness.run(
        harness.db.end_users.insert_one(
            {
                "_id": user_oid,
                "main_id": main_id,
                "status": "active",
                "name": f"t02-{user_oid}",
                "created_at": now,
                "updated_at": now,
            }
        )
    )
    harness.run(
        harness.db.end_user_sessions.insert_one(
            {
                "token_id": token_id,
                "status": "active",
                "user_id": user_oid,
                "main_id": main_id,
                "expires_at": now + timedelta(hours=1),
                "created_at": now,
                "updated_at": now,
            }
        )
    )
    return str(user_oid), build_session_token(SECRET, token_id)


def _seed_session(harness, *, owner_id: str, title: str = "t02") -> str:
    session = harness.run(
        ConversationRepository(harness.db).create(
            tenant_id=TENANT, user_id=owner_id, title=title
        )
    )
    return str(session["_id"])


def _add_participant(harness, session_id: str, user_id: str) -> None:
    harness.run(
        SessionParticipantsRepository(harness.db).add(
            tenant_id=TENANT, conversation_id=session_id, user_id=user_id
        )
    )


def _remove_participant(harness, session_id: str, user_id: str) -> None:
    harness.run(
        SessionParticipantsRepository(harness.db).remove(
            session_id, tenant_id=TENANT, user_id=user_id
        )
    )


def _append_message(
    harness, session_id: str, *, message_id: str, role: str, content: str
) -> None:
    harness.run(
        ConversationRepository(harness.db).append_message(
            conversation_id=session_id,
            tenant_id=TENANT,
            user_id=OWNER,
            role=role,
            content=content,
            message_id=message_id,
        )
    )


def _mark_active_run(
    harness, session_id: str, *, message_id: str, run_id: str
) -> None:
    harness.run(
        ConversationRepository(harness.db).mark_active_run(
            conversation_id=session_id,
            tenant_id=TENANT,
            user_id=OWNER,
            message_id=message_id,
            run_id=run_id,
        )
    )


def _seed_execution_rows(harness, message_id: str, seqs: list[int]) -> None:
    """Durable projection rows in the shape ``list_for_message`` reads."""
    for seq in seqs:
        harness.run(
            harness.db[PROJECTIONS].insert_one(
                {
                    "message_id": message_id,
                    "tenant_id": TENANT,
                    "stream_seq": seq,
                    "v": 1,
                    "ts": None,
                    "type": "item.delta",
                    "item_kind": "final_answer",
                    "item_id": f"item-{seq}",
                    "event_id": f"evt-{message_id}-{seq}",
                    "payload": {"text": f"step-{seq}", "provisional": True},
                }
            )
        )


async def _advance_durable(harness, session_id: str, *, message_id: str) -> None:
    """Mid-stream durable advance via real repositories (no nested run)."""
    repo = ConversationRepository(harness.db)
    await repo.append_message(
        conversation_id=session_id,
        tenant_id=TENANT,
        user_id=OWNER,
        role="assistant",
        content="",
        message_id=message_id,
    )
    await repo.mark_active_run(
        conversation_id=session_id,
        tenant_id=TENANT,
        user_id=OWNER,
        message_id=message_id,
        run_id=f"run-{message_id}",
    )
    for seq in (1, 2):
        await harness.db[PROJECTIONS].insert_one(
            {
                "message_id": message_id,
                "tenant_id": TENANT,
                "stream_seq": seq,
                "v": 1,
                "ts": None,
                "type": "item.delta",
                "item_kind": "final_answer",
                "item_id": f"item-{message_id}-{seq}",
                "event_id": f"evt-{message_id}-{seq}",
                "payload": {"text": f"step-{seq}", "provisional": True},
            }
        )


async def _remove_member(harness, session_id: str, user_id: str) -> None:
    await SessionParticipantsRepository(harness.db).remove(
        session_id, tenant_id=TENANT, user_id=user_id
    )


# ---------------------------------------------------------------------------
# ASGI helpers: real endpoint over ASGITransport (no gateway proxy)
# ---------------------------------------------------------------------------

SSE_HEADERS = {
    "content-type": "text/event-stream; charset=utf-8",
    "cache-control": "no-cache, no-transform",
    "connection": "keep-alive",
    "x-accel-buffering": "no",
}


def _app():
    from app.main import app as fastapi_app

    return fastapi_app


def _transport() -> httpx.ASGITransport:
    return httpx.ASGITransport(app=_app())


def _frames(text: str) -> list[dict[str, Any]]:
    """Parse accumulated SSE text; heartbeat comments are not frames."""
    parsed: list[dict[str, Any]] = []
    for block in text.split("\n\n"):
        if not block.strip() or block.lstrip().startswith(":"):
            continue
        frame: dict[str, Any] = {
            "id": None,
            "event": None,
            "data": None,
            "block": block,
        }
        for line in block.split("\n"):
            if line.startswith("id: "):
                frame["id"] = line[len("id: ") :]
            elif line.startswith("event: "):
                frame["event"] = line[len("event: ") :]
            elif line.startswith("data: "):
                frame["data"] = line[len("data: ") :]
        parsed.append(frame)
    return parsed


async def _open_stream(app, session_id: str, *, token: str | None) -> SimpleNamespace:
    """Drive the real ASGI app directly; body messages arrive as they are sent.

    httpx's ASGITransport buffers a whole response before returning it, so an
    endless SSE body can never be read through it; this harness feeds the app
    the real scope/events and exposes response.start plus the body-message
    queue, and ``disconnect`` is the client-cancel signal.
    """
    raw_headers = [(b"host", b"testserver")]
    if token is not None:
        raw_headers.append((b"authorization", f"Bearer {token}".encode("latin-1")))
    path = _live_url(session_id)
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("latin-1"),
        "query_string": b"",
        "root_path": "",
        "headers": raw_headers,
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 12345),
    }
    state = SimpleNamespace(
        status=None,
        headers={},
        queue=asyncio.Queue(),
        done=asyncio.Event(),
        disconnect=asyncio.Event(),
        started=asyncio.Event(),
        sent_request=False,
        task=None,
    )

    async def receive():
        if not state.sent_request:
            state.sent_request = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await state.disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            state.status = message["status"]
            state.headers = {
                key.decode("latin-1").lower(): value.decode("latin-1")
                for key, value in message.get("headers", [])
            }
            state.started.set()
        elif message["type"] == "http.response.body":
            if message.get("body"):
                state.queue.put_nowait(message["body"])
            if not message.get("more_body", False):
                state.done.set()

    state.task = asyncio.ensure_future(app(scope, receive, send))
    started = asyncio.ensure_future(state.started.wait())
    await asyncio.wait(
        {started, state.task}, timeout=8.0, return_when=asyncio.FIRST_COMPLETED
    )
    started.cancel()
    if not state.started.is_set():
        if state.task.done():
            exception = state.task.exception()
            if exception is not None:
                raise exception
            raise AssertionError("application finished before response start")
        state.task.cancel()
        raise AssertionError("response start timed out")
    return state


async def _read_until(state, predicate, *, timeout: float = 8.0) -> str:
    """Accumulate body messages until ``predicate`` holds or the body ends."""
    buffer = ""
    deadline = time.monotonic() + timeout
    while True:
        if state.queue.empty() and state.done.is_set():
            return buffer
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError(f"stream read timed out; arrived={buffer!r}")
        try:
            chunk = await asyncio.wait_for(state.queue.get(), timeout=remaining)
        except asyncio.TimeoutError:
            raise AssertionError(
                f"stream read timed out; arrived={buffer!r}"
            ) from None
        buffer += chunk.decode("utf-8")
        if predicate(buffer):
            return buffer


async def _drain(state, *, timeout: float = 8.0) -> str:
    """Read to EOF within the deadline; EOF is the point."""
    return await _read_until(state, lambda _buffer: False, timeout=timeout)


async def _close_stream(state, *, timeout: float = 8.0) -> None:
    """Client disconnect: the app must cancel the generator and return."""
    state.disconnect.set()
    try:
        await asyncio.wait_for(state.task, timeout=timeout)
    except asyncio.TimeoutError:
        raise AssertionError("stream did not close on client disconnect") from None


def _session_doc(harness, session_id: str) -> Any:
    return harness.run(
        harness.db.chat_sessions.find_one({"_id": ObjectId(session_id)})
    )


def _expect_not_found(response: httpx.Response) -> None:
    assert response.status_code == 404
    assert response.json()["detail"] == {
        "code": "session_not_found",
        "message": "Session not found",
    }


def _live_url(session_id: str) -> str:
    return f"/api/sessions/{session_id}/live"


# ---------------------------------------------------------------------------
# QA-happy (plan row L106): open, advance, framed data, clean cancel
# ---------------------------------------------------------------------------


def test_owner_cold_attach_receives_durable_frames_and_closes_cleanly(live_env):
    harness = live_env
    owner_id, owner_token = _seed_principal(harness)
    session_id = _seed_session(harness, owner_id=owner_id)
    _append_message(
        harness, session_id, message_id="msg-t02-owner", role="assistant", content=""
    )
    _mark_active_run(
        harness, session_id, message_id="msg-t02-owner", run_id="run-t02-owner"
    )
    _seed_execution_rows(harness, "msg-t02-owner", [1, 2])
    before = _session_doc(harness, session_id)

    async def scenario() -> str:
        state = await _open_stream(_app(), session_id, token=owner_token)
        assert state.status == 200
        for name, value in SSE_HEADERS.items():
            assert state.headers[name] == value
        text = await _read_until(
            state,
            lambda buffer: buffer.count("event: execution") >= 2
            and buffer.count("data: ") >= 3,
        )
        await _close_stream(state)
        return text

    frames = _frames(harness.run(scenario()))
    assert [frame["event"] for frame in frames] == [
        "turn.started",
        "execution",
        "execution",
    ]
    assert all(frame["id"] is not None for frame in frames)
    started = json.loads(frames[0]["data"])
    assert started["session_id"] == session_id
    assert started["message_id"] == "msg-t02-owner"
    assert started["run_id"] == "run-t02-owner"
    executions = [json.loads(frame["data"]) for frame in frames[1:]]
    assert [row["stream_seq"] for row in executions] == [1, 2]
    assert [row["payload"]["text"] for row in executions] == ["step-1", "step-2"]
    assert _session_doc(harness, session_id) == before


def test_active_participant_receives_frames_advanced_mid_stream(live_env):
    harness = live_env
    owner_id, _owner_token = _seed_principal(harness)
    participant_id, participant_token = _seed_principal(harness)
    session_id = _seed_session(harness, owner_id=owner_id)
    _add_participant(harness, session_id, participant_id)

    async def scenario() -> str:
        state = await _open_stream(_app(), session_id, token=participant_token)
        assert state.status == 200
        await _read_until(state, lambda buffer: ": heartbeat" in buffer)
        await _advance_durable(
            harness, session_id, message_id="msg-t02-midstream"
        )
        text = await _read_until(
            state,
            lambda buffer: buffer.count("event: execution") >= 2
            and buffer.count("data: ") >= 3,
        )
        await _close_stream(state)
        return text

    frames = _frames(harness.run(scenario()))
    assert frames[0]["event"] == "turn.started"
    assert [frame["event"] for frame in frames].count("execution") == 2
    assert json.loads(frames[0]["data"])["message_id"] == "msg-t02-midstream"
    assert [
        json.loads(frame["data"])["payload"]["text"]
        for frame in frames
        if frame["event"] == "execution"
    ] == ["step-1", "step-2"]


def test_idle_stream_heartbeats_and_closes_cleanly_on_cancel(live_env):
    harness = live_env
    owner_id, owner_token = _seed_principal(harness)
    session_id = _seed_session(harness, owner_id=owner_id)
    before = _session_doc(harness, session_id)

    async def scenario() -> str:
        state = await _open_stream(_app(), session_id, token=owner_token)
        assert state.status == 200
        text = await _read_until(
            state, lambda buffer: buffer.count(": heartbeat") >= 3
        )
        await _close_stream(state)
        return text

    text = harness.run(scenario())
    assert text.count(": heartbeat") >= 3
    assert _frames(text) == []
    assert _session_doc(harness, session_id) == before


# ---------------------------------------------------------------------------
# QA-failure (plan row L107): mid-stream membership loss
# ---------------------------------------------------------------------------


def test_membership_change_mid_stream_revokes_with_one_no_id_terminal_frame(
    live_env,
):
    harness = live_env
    owner_id, _owner_token = _seed_principal(harness)
    participant_id, participant_token = _seed_principal(harness)
    session_id = _seed_session(harness, owner_id=owner_id)
    _add_participant(harness, session_id, participant_id)
    _append_message(
        harness, session_id, message_id="msg-t02-revoked", role="assistant", content=""
    )
    _mark_active_run(
        harness, session_id, message_id="msg-t02-revoked", run_id="run-t02-revoked"
    )
    _seed_execution_rows(harness, "msg-t02-revoked", [1])

    async def scenario() -> str:
        state = await _open_stream(_app(), session_id, token=participant_token)
        assert state.status == 200
        seen = await _read_until(
            state, lambda buffer: "event: execution" in buffer
        )
        await _remove_member(harness, session_id, participant_id)
        text = seen + await _drain(state)
        await _close_stream(state)
        return text

    frames = _frames(harness.run(scenario()))
    revoked = [
        frame for frame in frames if frame["event"] == EVENT_ACCESS_REVOKED
    ]
    assert len(revoked) == 1
    assert frames[-1] is revoked[0]
    assert revoked[0]["id"] is None
    assert "id: " not in revoked[0]["block"]
    assert json.loads(revoked[0]["data"]) == {
        "session_id": session_id,
        "reason": "participant_removed",
    }
    tail = frames[frames.index(revoked[0]) + 1 :]
    assert all(frame["event"] != "execution" for frame in tail)


def test_member_removed_mid_stream_receives_no_later_execution_event(live_env):
    harness = live_env
    owner_id, _owner_token = _seed_principal(harness)
    participant_id, participant_token = _seed_principal(harness)
    session_id = _seed_session(harness, owner_id=owner_id)
    _add_participant(harness, session_id, participant_id)
    _append_message(
        harness, session_id, message_id="msg-t02-late", role="assistant", content=""
    )
    _mark_active_run(
        harness, session_id, message_id="msg-t02-late", run_id="run-t02-late"
    )
    _seed_execution_rows(harness, "msg-t02-late", [1])

    async def scenario() -> str:
        state = await _open_stream(_app(), session_id, token=participant_token)
        assert state.status == 200
        seen = await _read_until(
            state, lambda buffer: "event: execution" in buffer
        )
        await _remove_member(harness, session_id, participant_id)
        await _advance_durable(
            harness, session_id, message_id="msg-t02-after-removal"
        )
        text = seen + await _drain(state)
        await _close_stream(state)
        return text

    frames = _frames(harness.run(scenario()))
    executions = [frame for frame in frames if frame["event"] == "execution"]
    revoked = [
        frame for frame in frames if frame["event"] == EVENT_ACCESS_REVOKED
    ]
    assert len(executions) == 1
    assert len(revoked) == 1
    assert frames[-1] is revoked[0]
    assert "msg-t02-after-removal" not in "".join(
        frame["data"] or "" for frame in frames
    )


def test_missing_and_malformed_bearer_are_401_invalid_token(live_env):
    harness = live_env
    owner_id, _owner_token = _seed_principal(harness)
    session_id = _seed_session(harness, owner_id=owner_id)

    async def scenario():
        async with httpx.AsyncClient(
            transport=_transport(), base_url="http://testserver"
        ) as client:
            return (
                await client.get(_live_url(session_id)),
                await client.get(
                    _live_url(session_id),
                    headers={"Authorization": "Bearer not-a-real-token"},
                ),
                await client.get(
                    _live_url(session_id), headers={"Authorization": ""}
                ),
            )

    for response in harness.run(scenario()):
        assert response.status_code == 401
        assert response.json()["detail"] == "invalid_token"


def test_cross_tenant_authenticated_probe_is_404(live_env):
    harness = live_env
    owner_id, _owner_token = _seed_principal(harness)
    _stranger_id, stranger_token = _seed_principal(harness, main_id=OTHER_TENANT)
    session_id = _seed_session(harness, owner_id=owner_id)

    async def scenario():
        async with httpx.AsyncClient(
            transport=_transport(), base_url="http://testserver"
        ) as client:
            return await client.get(
                _live_url(session_id),
                headers={"Authorization": f"Bearer {stranger_token}"},
            )

    _expect_not_found(harness.run(scenario()))


def test_never_member_is_404(live_env):
    harness = live_env
    owner_id, _owner_token = _seed_principal(harness)
    _stranger_id, stranger_token = _seed_principal(harness)
    session_id = _seed_session(harness, owner_id=owner_id)

    async def scenario():
        async with httpx.AsyncClient(
            transport=_transport(), base_url="http://testserver"
        ) as client:
            return await client.get(
                _live_url(session_id),
                headers={"Authorization": f"Bearer {stranger_token}"},
            )

    _expect_not_found(harness.run(scenario()))


def test_removed_member_is_404(live_env):
    harness = live_env
    owner_id, _owner_token = _seed_principal(harness)
    participant_id, participant_token = _seed_principal(harness)
    session_id = _seed_session(harness, owner_id=owner_id)
    _add_participant(harness, session_id, participant_id)
    _remove_participant(harness, session_id, participant_id)

    async def scenario():
        async with httpx.AsyncClient(
            transport=_transport(), base_url="http://testserver"
        ) as client:
            return await client.get(
                _live_url(session_id),
                headers={"Authorization": f"Bearer {participant_token}"},
            )

    _expect_not_found(harness.run(scenario()))


# ---------------------------------------------------------------------------
# Admission boundary (plan rows L106-L107): the real DshChatService
# ---------------------------------------------------------------------------


class _CompletingRunner:
    """Replaces the DSH turn runner: in flight until released, then final."""

    def __init__(self, chat) -> None:
        self.chat = chat
        self.release = asyncio.Event()

    async def __call__(
        self,
        *,
        binding,
        message_id,
        request_id,
        text,
        temporal_context,
        turn_context,
        live_stream,
    ):
        await self.release.wait()
        await self.chat._finalizer.finalize(
            binding=binding, message_id=message_id, status="completed"
        )
        return "completed"


@pytest.fixture
def admission_lane(real_mongo_db, monkeypatch):
    harness = real_mongo_db
    monkeypatch.setattr(
        chat_service_module, "get_db", lambda: harness.db, raising=False
    )
    harness.run(SessionParticipantsRepository(harness.db).ensure_indexes())
    harness.run(KernelBindingRepository(harness.db).ensure_indexes())

    owner_id = str(ObjectId())
    participant_id = str(ObjectId())
    session_id = str(
        harness.run(
            ConversationRepository(harness.db).create(
                tenant_id=TENANT, user_id=owner_id, title="t02-admission"
            )
        )["_id"]
    )
    _add_participant(harness, session_id, participant_id)
    binding_id = f"bind-{uuid.uuid4().hex}"
    now = datetime.utcnow()
    harness.run(
        harness.db.agent_kernel_bindings.insert_one(
            {
                "binding_id": binding_id,
                "conversation_id": session_id,
                "tenant_id": TENANT,
                "user_id": owner_id,
                "current": True,
                "status": "idle",
                "active_turn": None,
                "kernel_session_id": f"ks-{uuid.uuid4().hex}",
                "execution_location": "server",
                "profile_version": "pv-t02",
                "model_instance_id": "model-a",
                "created_at": now,
                "updated_at": now,
            }
        )
    )
    chat = DshChatService(
        gateway=SimpleNamespace(),
        coordinator=RuntimeCoordinator(
            SimpleNamespace(), KernelBindingRepository(harness.db)
        ),
        conversations=ConversationRepository(harness.db),
        bindings=KernelBindingRepository(harness.db),
        events=KernelEventRepository(harness.db),
        profiles=SimpleNamespace(),
        kernel_version="test-kernel",
    )
    runner = _CompletingRunner(chat)
    chat._turn_runner.run = runner

    async def passthrough(binding, *, tenant_id, user_id, model_instance_id=None):
        return SimpleNamespace(binding=binding)

    chat._profile_sync.synchronize = passthrough
    monkeypatch.setattr(
        chat_service_module, "_STREAM_AUTH_RECHECK_SECONDS", 0.02, raising=False
    )
    return SimpleNamespace(
        harness=harness,
        chat=chat,
        runner=runner,
        session_id=session_id,
        owner_id=owner_id,
        participant_id=participant_id,
        binding_id=binding_id,
    )


def _prepare(chat, harness, session_id: str, *, user_id: str):
    return harness.run(
        chat.prepare_turn(
            tenant_id=TENANT,
            user_id=user_id,
            conversation_id=session_id,
            text="t02 turn",
            model_instance_id="model-a",
            timezone_name="UTC",
            images=[],
            documents=[],
        )
    )


def _binding_row(harness, conversation_id: str) -> Any:
    return harness.run(
        harness.db.agent_kernel_bindings.find_one(
            {"conversation_id": conversation_id, "current": True}
        )
    )


def _messages(harness, session_id: str) -> list[Any]:
    return list(
        harness.run(
            ConversationRepository(harness.db).list_messages(TENANT, session_id)
        )
    )


def test_barrier_removal_between_precheck_and_claim_rolls_back_without_orphans(
    admission_lane, monkeypatch
):
    lane = admission_lane
    harness = lane.harness
    captured: dict[str, Any] = {}
    real_claim = lane.chat._bindings.claim_turn_authorized

    async def claim_after_removal(binding_id, **kwargs):
        captured.setdefault("message_id", kwargs["message_id"])
        await SessionParticipantsRepository(harness.db).remove(
            lane.session_id, tenant_id=TENANT, user_id=lane.participant_id
        )
        return await real_claim(binding_id, **kwargs)

    monkeypatch.setattr(lane.chat._bindings, "claim_turn_authorized", claim_after_removal)

    with pytest.raises(SessionReadDeniedError):
        _prepare(lane.chat, harness, lane.session_id, user_id=lane.participant_id)

    assert _messages(harness, lane.session_id) == []
    binding = _binding_row(harness, lane.session_id)
    assert binding["status"] == "failed"
    assert binding["active_turn"]["status"] == "failed"

    lane.runner.release.set()
    owner_turn = _prepare(lane.chat, harness, lane.session_id, user_id=lane.owner_id)
    assert harness.run(lane.chat.wait_turn(owner_turn.message_id)) == "completed"
    messages = _messages(harness, lane.session_id)
    assert [str(row.get("role")) for row in messages] == ["user", "assistant"]
    assert captured["message_id"] not in {
        str(row.get("message_id")) for row in messages
    }


def test_removal_before_send_lock_suppresses_the_in_flight_frame(admission_lane):
    lane = admission_lane
    harness = lane.harness
    turn = _prepare(lane.chat, harness, lane.session_id, user_id=lane.participant_id)

    async def scenario() -> str:
        live_stream = lane.chat._live_streams[turn.message_id]
        live_stream.publish({"type": "item.delta", "text": "suppressed"})
        await _remove_member(harness, lane.session_id, lane.participant_id)
        stream = lane.chat.stream(
            turn, tenant_id=TENANT, user_id=lane.participant_id
        )
        first = await asyncio.wait_for(stream.__anext__(), timeout=5)
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(stream.__anext__(), timeout=5)
        return first

    assert json.loads(harness.run(scenario())) == {
        "type": "session.access.revoked",
        "session_id": lane.session_id,
        "reason": "participant_removed",
    }
    lane.runner.release.set()
    assert harness.run(lane.chat.wait_turn(turn.message_id)) == "completed"


def test_write_before_removal_permits_only_that_frame_then_revokes(admission_lane):
    lane = admission_lane
    harness = lane.harness
    turn = _prepare(lane.chat, harness, lane.session_id, user_id=lane.participant_id)

    async def scenario():
        live_stream = lane.chat._live_streams[turn.message_id]
        live_stream.publish({"type": "item.delta", "text": "permitted"})
        stream = lane.chat.stream(
            turn, tenant_id=TENANT, user_id=lane.participant_id
        )
        first = await asyncio.wait_for(stream.__anext__(), timeout=5)
        await _remove_member(harness, lane.session_id, lane.participant_id)
        second = await asyncio.wait_for(stream.__anext__(), timeout=5)
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(stream.__anext__(), timeout=5)
        return first, second

    first, second = harness.run(scenario())
    first_row = json.loads(first)
    assert first_row["type"] == "item.delta"
    assert first_row["text"] == "permitted"
    assert first_row["session_id"] == lane.session_id
    assert json.loads(second) == {
        "type": "session.access.revoked",
        "session_id": lane.session_id,
        "reason": "participant_removed",
    }
    lane.runner.release.set()
    assert harness.run(lane.chat.wait_turn(turn.message_id)) == "completed"
