"""Real-mongod coverage for the live-event poll endpoint (todo 7).

Todo 7: the poll endpoint authorises by CONVERSATION membership, not by
viewer. A participant may follow another author's in-flight run, and any
member's poll drives the terminal/crash recovery (``ingest_once``).

TDD phases recorded in this module:
- baseline characterization (this file, first run on the UNCHANGED code),
- failing-first proofs for the new behaviour (RED),
- the green run after the conversation-scoped implementation.
"""

# allow: SIZE_OK — one cohesive seam (the event-poll endpoint + the poll
# recovery path), pinned to the frozen plan's todo-7 QA matrix; mirrors
# T04/T06's pinned single-file test matrices.

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pytest
from bson import ObjectId
from fastapi import HTTPException

import app.api.endpoints.dsh_chat as dsh_chat
from app.api.endpoints.dsh_chat import chat_message_events
from app.dsh_runtime.application import dsh_runtime_application
from app.dsh_runtime.bindings import KernelBindingRepository
from app.dsh_runtime.chat_service import DshChatService
from app.dsh_runtime.conversation import ConversationRepository
from app.dsh_runtime.conversation.participants_repository import (
    SessionParticipantsRepository,
)
from app.dsh_runtime.contracts.events import KernelEventEnvelope, KernelEventSource
from app.dsh_runtime.events import KernelEventRepository
from app.dsh_runtime.profile.models import RuntimeProfileSnapshot
from app.dsh_runtime.runtime_coordinator import RuntimeCoordinator

TENANT = "tenant-a"
OTHER_TENANT = "tenant-b"
OWNER = "user-owner"
PARTICIPANT = "user-participant"
NON_MEMBER = "user-nonmember"
KERNEL = "kernel-test"
PROFILE_VERSION = "profile-v1"
MSG = "msg-inflight"


# ---------------------------------------------------------------------------
# Fakes — the narrowest seams. The gateway wraps an HTTP transport to the DSH
# Runtime Host (unrunnable in tests); the fake replays recorded native events.
# ---------------------------------------------------------------------------


class _FakeRuntime:
    def __init__(self, *, runtime_id: str, kernel_version: str) -> None:
        self.runtime_id = runtime_id
        self.kernel_version = kernel_version


class _FakeGateway:
    """In-memory DSH gateway fake at the poll-recovery seam.

    ``events_once`` mirrors the real contract (a kernel session's events
    after a cursor); discovery/attach/resume are no-ops. No HTTP, no sleeps.
    """

    def __init__(self, events: list[KernelEventEnvelope] | None = None) -> None:
        self._events = list(events or [])

    async def events_once(self, session_id: str, after_cursor: int = 0) -> list[KernelEventEnvelope]:
        return [
            event
            for event in self._events
            if event.session_id == session_id and event.cursor > int(after_cursor)
        ]

    async def discover_runtime(self, *, tenant_id: str, profile_version: str, isolation_key: str) -> _FakeRuntime:
        return _FakeRuntime(runtime_id="runtime-test", kernel_version="test-kernel")

    def attach_session(self, **kwargs: Any) -> None:
        return None

    async def resume_session(self, session_id: str) -> None:
        return None


class _FakeProfiles:
    """``RuntimeProfilePublisher`` fake: ``get`` returns a tool-less snapshot."""

    def __init__(self) -> None:
        self._snapshots: dict[str, RuntimeProfileSnapshot] = {}

    async def get(self, profile_version: str) -> RuntimeProfileSnapshot:
        snapshot = self._snapshots.get(profile_version)
        if snapshot is None:
            snapshot = RuntimeProfileSnapshot(
                profile_version=profile_version,
                content_hash="0" * 64,
                tenant_id=TENANT,
                model_source_tenant_id=TENANT,
                model_instance_id="model-1",
                provider_id="provider-1",
                provider_type="openai_compatible",
                provider_name="Provider",
                model_name="Model",
                display_name="Model",
                capabilities=(),
            )
            self._snapshots[profile_version] = snapshot
        return snapshot


# ---------------------------------------------------------------------------
# Seed helpers — production write paths only
# ---------------------------------------------------------------------------


def _users() -> tuple[dict[str, str], dict[str, str]]:
    """Bearer-token -> seeded end-user row id; _identity resolves user_id from it.

    Production shape: the session doc's ``user_id`` (and the binding and
    participant rows) carry the STRING of the end_users ``_id``, which is
    exactly what ``_identity`` returns for the bearer.
    """
    users = {
        OWNER: str(ObjectId()),
        PARTICIPANT: str(ObjectId()),
        NON_MEMBER: str(ObjectId()),
        "user-othertenant": str(ObjectId()),
    }
    tenant_by_token = {
        OWNER: TENANT,
        PARTICIPANT: TENANT,
        NON_MEMBER: TENANT,
        "user-othertenant": OTHER_TENANT,
    }
    return users, tenant_by_token


def _identity_seam(users: dict[str, str], tenant_by_token: dict[str, str]):
    async def resolve(authorization: str | None):
        token = str(authorization or "").removeprefix("Bearer ").strip()
        oid = users.get(token)
        if oid is None:
            raise LookupError(f"no seeded end-user for bearer token {token!r}")
        return {"user": {"_id": oid, "status": "active"}, "main_id": tenant_by_token[token]}

    return resolve


def _seed_session(harness, *, owner: str, tenant: str = TENANT) -> str:
    async def seed():
        row = {
            "user_id": owner,
            "main_id": tenant,
            "title": "Shared chat",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        result = await harness.db.chat_sessions.insert_one(row)
        return str(result.inserted_id)

    return harness.run(seed())


def _seed_message(harness, session_id: str, *, user_id: str, message_id: str, tenant: str = TENANT) -> None:
    async def seed():
        await harness.db.chat_messages.insert_one(
            {
                "session_id": ObjectId(session_id),
                "user_id": user_id,
                "main_id": tenant,
                "seq": 1,
                "role": "assistant",
                "content": "",
                "message_id": message_id,
                "execution_events": [],
                "created_at": datetime.utcnow(),
                "runtime_owner": "dsh",
            }
        )

    harness.run(seed())


def _bindings_repo(harness) -> KernelBindingRepository:
    repo = KernelBindingRepository(harness.db)
    harness.run(repo.ensure_indexes())
    return repo


def _seed_binding(harness, session_id: str, *, user_id: str, message_id: str | None = None, tenant: str = TENANT) -> dict[str, Any]:
    repo = _bindings_repo(harness)
    binding = harness.run(
        repo.create(
            tenant_id=tenant,
            user_id=user_id,
            conversation_id=session_id,
            kernel_session_id=KERNEL,
            runtime_id="runtime-test",
            profile_version=PROFILE_VERSION,
            model_instance_id="model-1",
            kernel_version="test-kernel",
        )
    )
    if message_id is not None:
        binding = harness.run(
            repo.claim_turn(
                str(binding["binding_id"]),
                message_id=message_id,
                request_id=f"turn-{message_id}",
                turn_context={},
                turn_metadata={},
            )
        )
    return binding


def _envelope(event_id: str, cursor: int, event_type: str, **payload: Any) -> KernelEventEnvelope:
    return KernelEventEnvelope(
        event_id=event_id,
        runtime_id="runtime-test",
        session_id=KERNEL,
        profile_version=PROFILE_VERSION,
        cursor=cursor,
        type=event_type,
        occurred_at=datetime.now(timezone.utc),
        payload=payload,
        source=KernelEventSource(kernel_version="test-kernel"),
    )


def _ingest_projection(harness, binding: dict[str, Any], message_id: str, event: KernelEventEnvelope) -> None:
    """Seed a durable projection through the REAL write path (write-time
    attribution: tenant/user_id from the binding, i.e. the run's author)."""
    repo = KernelEventRepository(harness.db)
    harness.run(repo.ensure_indexes())
    harness.run(
        repo.ingest(
            event,
            tenant_id=str(binding["tenant_id"]),
            user_id=str(binding["user_id"]),
            conversation_id=str(binding["conversation_id"]),
            message_id=message_id,
        )
    )


def _join(harness, session_id: str, *, user_id: str, tenant: str = TENANT) -> None:
    harness.run(SessionParticipantsRepository(harness.db).add(tenant_id=tenant, conversation_id=session_id, user_id=user_id))


def _remove(harness, session_id: str, *, user_id: str, tenant: str = TENANT) -> None:
    harness.run(SessionParticipantsRepository(harness.db).remove(session_id, tenant_id=tenant, user_id=user_id))


def _chat_service(harness, gateway: _FakeGateway) -> DshChatService:
    bindings = _bindings_repo(harness)
    return DshChatService(
        gateway=gateway,
        coordinator=RuntimeCoordinator(gateway, bindings),
        conversations=ConversationRepository(harness.db),
        bindings=bindings,
        events=KernelEventRepository(harness.db),
        profiles=_FakeProfiles(),
        kernel_version="test-kernel",
    )


def _wire(harness, monkeypatch, chat_service: DshChatService, users: dict[str, str], tenant_by_token: dict[str, str]) -> None:
    monkeypatch.setattr(dsh_runtime_application, "chat", chat_service)
    monkeypatch.setattr(dsh_chat, "_resolve_session_user", _identity_seam(users, tenant_by_token))
    # raising=False: the pre-T07 endpoint module does not import get_db yet;
    # the attribute is unused until the membership gate lands.
    monkeypatch.setattr(dsh_chat, "get_db", lambda: harness.db, raising=False)


def _poll(harness, message_id: str, *, token: str):
    return harness.run(
        chat_message_events(
            message_id=message_id,
            after=0,
            after_cursor=None,
            authorization=f"Bearer {token}",
        )
    )


# ---------------------------------------------------------------------------
# Baseline characterization (passed on the UNCHANGED code, stays green)
# ---------------------------------------------------------------------------


def test_owner_poll_of_own_in_flight_message_returns_the_events(real_mongo_db, monkeypatch):
    harness = real_mongo_db
    users, tenant_by_token = _users()
    session_id = _seed_session(harness, owner=users[OWNER])
    _seed_message(harness, session_id, user_id=users[OWNER], message_id=MSG)
    _seed_binding(harness, session_id, user_id=users[OWNER], message_id=MSG)
    gateway = _FakeGateway(events=[_envelope("evt-start", 1, "turn.started")])
    _wire(harness, monkeypatch, _chat_service(harness, gateway), users, tenant_by_token)

    response = _poll(harness, MSG, token=OWNER)

    assert response.code == 0
    data = response.data
    assert data["status"] == "live"
    assert data["live"] is True
    assert [row["type"] for row in data["events"]] == ["run.started"]


def test_owner_poll_of_a_terminal_message_returns_the_persisted_events(real_mongo_db, monkeypatch):
    harness = real_mongo_db
    users, tenant_by_token = _users()
    session_id = _seed_session(harness, owner=users[OWNER])
    _seed_message(harness, session_id, user_id=users[OWNER], message_id=MSG)
    binding = _seed_binding(harness, session_id, user_id=users[OWNER], message_id=MSG)
    harness.run(_bindings_repo(harness).finish_turn(str(binding["binding_id"]), message_id=MSG, status="completed"))
    _ingest_projection(
        harness, binding, MSG, _envelope("evt-done", 2, "turn.completed", reason={"kind": "stop"})
    )
    _wire(harness, monkeypatch, _chat_service(harness, _FakeGateway()), users, tenant_by_token)

    response = _poll(harness, MSG, token=OWNER)

    assert response.code == 0
    data = response.data
    assert data["status"] == "completed"
    assert data["live"] is False
    assert [row["type"] for row in data["events"]] == ["run.completed"]


def test_cross_tenant_caller_poll_receives_404(real_mongo_db, monkeypatch):
    harness = real_mongo_db
    users, tenant_by_token = _users()
    session_id = _seed_session(harness, owner=users[OWNER])
    _seed_message(harness, session_id, user_id=users[OWNER], message_id=MSG)
    _seed_binding(harness, session_id, user_id=users[OWNER], message_id=MSG)
    _wire(harness, monkeypatch, _chat_service(harness, _FakeGateway()), users, tenant_by_token)

    with pytest.raises(HTTPException) as excinfo:
        _poll(harness, MSG, token="user-othertenant")

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "message_not_found"


def test_unknown_message_id_receives_a_clean_404(real_mongo_db, monkeypatch):
    harness = real_mongo_db
    users, tenant_by_token = _users()
    session_id = _seed_session(harness, owner=users[OWNER])
    _wire(harness, monkeypatch, _chat_service(harness, _FakeGateway()), users, tenant_by_token)

    with pytest.raises(HTTPException) as excinfo:
        _poll(harness, "msg-does-not-exist", token=OWNER)

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "message_not_found"


def test_path_like_message_id_receives_a_clean_404(real_mongo_db, monkeypatch):
    harness = real_mongo_db
    users, tenant_by_token = _users()
    session_id = _seed_session(harness, owner=users[OWNER])
    _wire(harness, monkeypatch, _chat_service(harness, _FakeGateway()), users, tenant_by_token)

    with pytest.raises(HTTPException) as excinfo:
        _poll(harness, "../../../etc/passwd", token=OWNER)

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "message_not_found"


# ---------------------------------------------------------------------------
# New behaviour (RED on the unchanged code)
# ---------------------------------------------------------------------------


def test_participant_poll_of_the_owners_in_flight_message_matches_the_owners_view(real_mongo_db, monkeypatch):
    # QA happy (plan todo 7): a participant polls the owner's in-flight
    # message and receives a non-404 snapshot whose live flag matches the
    # owner's view. The participant polls FIRST: their poll alone must
    # produce the events (the recovery ingest runs for any member).
    harness = real_mongo_db
    users, tenant_by_token = _users()
    session_id = _seed_session(harness, owner=users[OWNER])
    _seed_message(harness, session_id, user_id=users[OWNER], message_id=MSG)
    _seed_binding(harness, session_id, user_id=users[OWNER], message_id=MSG)
    _join(harness, session_id, user_id=users[PARTICIPANT])
    gateway = _FakeGateway(events=[_envelope("evt-start", 1, "turn.started")])
    _wire(harness, monkeypatch, _chat_service(harness, gateway), users, tenant_by_token)

    participant_view = _poll(harness, MSG, token=PARTICIPANT)
    owner_view = _poll(harness, MSG, token=OWNER)

    assert participant_view.code == 0
    assert participant_view.data["events"] == owner_view.data["events"]
    assert participant_view.data["live"] == owner_view.data["live"]
    assert participant_view.data["live"] is True


def test_non_member_poll_receives_404(real_mongo_db, monkeypatch):
    # QA failure (plan todo 7): a non-member receives 404 - no existence
    # disclosure (pinned status matrix from todo 4).
    harness = real_mongo_db
    users, tenant_by_token = _users()
    session_id = _seed_session(harness, owner=users[OWNER])
    _seed_message(harness, session_id, user_id=users[OWNER], message_id=MSG)
    _seed_binding(harness, session_id, user_id=users[OWNER], message_id=MSG)
    _wire(harness, monkeypatch, _chat_service(harness, _FakeGateway()), users, tenant_by_token)

    with pytest.raises(HTTPException) as excinfo:
        _poll(harness, MSG, token=NON_MEMBER)

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "message_not_found"


def test_removed_participant_poll_receives_404(real_mongo_db, monkeypatch):
    # QA failure [review-3]: a participant whose row has removed_at set
    # receives 404.
    harness = real_mongo_db
    users, tenant_by_token = _users()
    session_id = _seed_session(harness, owner=users[OWNER])
    _seed_message(harness, session_id, user_id=users[OWNER], message_id=MSG)
    _seed_binding(harness, session_id, user_id=users[OWNER], message_id=MSG)
    _join(harness, session_id, user_id=users[PARTICIPANT])
    _remove(harness, session_id, user_id=users[PARTICIPANT])
    _wire(harness, monkeypatch, _chat_service(harness, _FakeGateway()), users, tenant_by_token)

    with pytest.raises(HTTPException) as excinfo:
        _poll(harness, MSG, token=PARTICIPANT)

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "message_not_found"


def test_participants_poll_drives_a_stalled_run_to_terminal_after_a_mid_run_restart(real_mongo_db, monkeypatch):
    # QA failure (plan todo 7): simulate a mid-run restart with the author's
    # client absent and assert a participant's poll drives the thread to a
    # terminal state. The runtime host still holds the kernel session and its
    # events - the fake gateway replays them, terminal included.
    harness = real_mongo_db
    users, tenant_by_token = _users()
    session_id = _seed_session(harness, owner=users[OWNER])
    _seed_message(harness, session_id, user_id=users[OWNER], message_id=MSG)
    _seed_binding(harness, session_id, user_id=users[OWNER], message_id=MSG)
    _join(harness, session_id, user_id=users[PARTICIPANT])
    gateway = _FakeGateway(
        events=[
            _envelope("evt-start", 1, "turn.started"),
            _envelope("evt-done", 2, "turn.completed", reason={"kind": "stop"}),
        ]
    )
    _wire(harness, monkeypatch, _chat_service(harness, gateway), users, tenant_by_token)

    response = _poll(harness, MSG, token=PARTICIPANT)  # the author never polls

    assert response.code == 0
    assert response.data["status"] == "completed"
    assert response.data["live"] is False
    assert [row["type"] for row in response.data["events"]] == ["run.started", "run.completed"]
    # The thread's durable lock reached terminal: no member is wedged.
    binding_row = harness.run(
        harness.db.agent_kernel_bindings.find_one({"active_turn.message_id": MSG})
    )
    assert binding_row["active_turn"]["status"] == "completed"
    # The recovered events are attributed to the AUTHOR (the binding
    # subject), never to the poller.
    projection = harness.run(
        harness.db.kernel_event_projections.find_one({"event_id": "dsh-v3:evt-done"})
    )
    assert projection["user_id"] == users[OWNER]


def test_an_abandoned_claim_reaches_terminal_via_a_non_author_members_poll(real_mongo_db, monkeypatch):
    # T6 handoff: the retry path must not wedge active_turn - an abandoned
    # claim left by a post-claim failure reaches terminal via the any-member
    # recovery poll BEFORE a retry can succeed.
    harness = real_mongo_db
    users, tenant_by_token = _users()
    session_id = _seed_session(harness, owner=users[OWNER])
    _seed_message(harness, session_id, user_id=users[OWNER], message_id=MSG)
    repo = _bindings_repo(harness)
    binding = harness.run(
        repo.create(
            tenant_id=TENANT,
            user_id=users[OWNER],
            conversation_id=session_id,
            kernel_session_id=KERNEL,
            runtime_id="runtime-test",
            profile_version=PROFILE_VERSION,
            model_instance_id="model-1",
            kernel_version="test-kernel",
        )
    )
    claimed = harness.run(
        repo.claim_turn(
            str(binding["binding_id"]),
            message_id=MSG,
            request_id="turn-abandoned",
            turn_context={},
            turn_metadata={},
        )
    )
    # Post-claim failure: the process died before the runner finalized - the
    # claim is abandoned and stale. The host completed the turn meanwhile.
    gateway = _FakeGateway(events=[_envelope("evt-done", 2, "turn.completed", reason={"kind": "stop"})])
    _join(harness, session_id, user_id=users[PARTICIPANT])
    _wire(harness, monkeypatch, _chat_service(harness, gateway), users, tenant_by_token)

    response = _poll(harness, MSG, token=PARTICIPANT)  # a NON-author member

    assert response.code == 0
    assert response.data["status"] == "completed"
    assert response.data["live"] is False
    # The retry can now claim the same binding: the wedge is gone.
    retried = harness.run(
        repo.claim_turn(
            str(claimed["binding_id"]),
            message_id="msg-retry",
            request_id="turn-retry",
            turn_context={},
            turn_metadata={},
        )
    )
    assert retried is not None
    assert retried["active_turn"]["message_id"] == "msg-retry"
