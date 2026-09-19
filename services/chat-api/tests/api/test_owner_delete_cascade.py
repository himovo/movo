# allow: SIZE_OK — one cohesive seam (the owner-delete cascade across
# participants, bindings and messages), pinned to the frozen plan's todo-12
# QA matrix; mirrors T04/T07/T08/T09/T10/T11's pinned single-file matrices.
"""Plan todo 12 — the owner's session delete cascades so nothing is orphaned.

The owner DELETE path (sessions.py) disposes the conversation, then deletes
the session row, ``chat_messages`` and ``execution_logs``. The defect this
todo fixes: the two ``delete_many`` calls were filtered by the deleter's
``user_id``, so participant-authored messages and execution logs SURVIVED an
owner delete, and only the owner-scoped current binding was disposed.

TDD phases recorded in this module:
- baseline characterization passed on the UNCHANGED code (the orphan defect
  demonstrated: participant-authored messages, logs and participant rows
  survived; only the owner-scoped current binding was disposed) — the four
  defect-pinning tests were SUPERSEDED by the cascade contract after the fix
  and removed; their verbatim run is recorded in T12-failure.txt,
- failing-first proofs for the cascade (RED),
- the green run after the conversation-scoped implementation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from bson import ObjectId
from fastapi import HTTPException

from app.api.endpoints import sessions as sessions_module
from app.api.endpoints.sessions import MessageAppend, MessageIn, delete_session
from app.dsh_runtime.application import dsh_runtime_application
from app.dsh_runtime.bindings.repository import KernelBindingRepository
from app.dsh_runtime.chat_service import DshChatService
from app.dsh_runtime.contracts import CancelSessionRequest
from app.dsh_runtime.conversation import ConversationRepository
from app.dsh_runtime.conversation.participants_repository import (
    SessionParticipantsRepository,
)
from app.dsh_runtime.events import KernelEventRepository
from app.dsh_runtime.profile.models import RuntimeProfileSnapshot
from app.dsh_runtime.runtime_coordinator import RuntimeCoordinator

TENANT = "tenant-owner-delete-cascade"

OWNER = "owner"
PARTICIPANT = "participant"
REMOVED = "removed"

TOKENS = {
    OWNER: "token-owner",
    PARTICIPANT: "token-participant",
    REMOVED: "token-removed",
}


# ---------------------------------------------------------------------------
# Fakes — the narrowest seams (T7's pattern). The gateway wraps an HTTP
# transport to the DSH Runtime Host (unrunnable in tests); the fake records
# the kernel-session work the dispose cascade performs.
# ---------------------------------------------------------------------------


class _FakeRuntime:
    runtime_id = "runtime-test"
    kernel_version = "test-kernel"


class _FakeGateway:
    """In-memory DSH gateway fake at the dispose seam.

    ``dispose_conversation``'s kernel-session work (cancel + dispose) runs
    against this fake; every call is recorded so the tests can assert the
    cascade really reached the runtime host. No HTTP, no sleeps.
    """

    def __init__(self) -> None:
        self.cancelled: list[str] = []
        self.disposed_sessions: list[str] = []

    async def discover_runtime(self, *, tenant_id: str, profile_version: str, isolation_key: str) -> _FakeRuntime:
        return _FakeRuntime()

    def attach_session(self, **kwargs: Any) -> None:
        return None

    async def resume_session(self, session_id: str) -> None:
        return None

    async def cancel(self, request: CancelSessionRequest) -> dict[str, Any]:
        self.cancelled.append(str(request.session_id))
        return {"ok": True}

    async def dispose_session(self, session_id: str) -> None:
        self.disposed_sessions.append(str(session_id))


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
# Fixture — production write paths only
# ---------------------------------------------------------------------------


@pytest.fixture
def owned_thread(real_mongo_db, monkeypatch):
    """A clean owner thread with one active participant, one removed
    participant, owner- and participant-authored messages and execution
    logs, and a rotated binding pair (superseded predecessor + current
    server binding) — everything the owner delete must cascade across.

    The REAL DshChatService is wired over real repos (T7's pattern): the
    dispose cascade is this todo's surface, so T11's recording stub is
    replaced; the gateway is faked at the HTTP seam and records calls.
    """
    harness = real_mongo_db
    harness.run(SessionParticipantsRepository(harness.db).ensure_indexes())
    monkeypatch.setattr(sessions_module, "get_db", lambda: harness.db)

    ids = {
        OWNER: ObjectId(),
        PARTICIPANT: ObjectId(),
        REMOVED: ObjectId(),
    }
    directory = {
        TOKENS[OWNER]: {"user": {"_id": ids[OWNER]}, "main_id": TENANT},
        TOKENS[PARTICIPANT]: {"user": {"_id": ids[PARTICIPANT]}, "main_id": TENANT},
        TOKENS[REMOVED]: {"user": {"_id": ids[REMOVED]}, "main_id": TENANT},
    }

    async def _resolve_session_user(authorization):
        token = str(authorization or "").split(" ", 1)[-1].strip()
        row = directory.get(token)
        if row is None:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return row

    monkeypatch.setattr(sessions_module, "_resolve_session_user", _resolve_session_user)

    session_oid = ObjectId()
    now = datetime.utcnow()
    harness.run(
        harness.db.chat_sessions.insert_one(
            {
                "_id": session_oid,
                "user_id": str(ids[OWNER]),
                "main_id": TENANT,
                "title": "Shared chat",
                "created_at": now,
                "updated_at": now,
            }
        )
    )
    harness.run(
        harness.db.chat_messages.insert_many(
            [
                {
                    "main_id": TENANT,
                    "session_id": session_oid,
                    "user_id": str(ids[OWNER]),
                    "role": "user",
                    "content": "owner message",
                    "message_id": None,
                    "seq": 1,
                    "created_at": now,
                },
                {
                    "main_id": TENANT,
                    "session_id": session_oid,
                    "user_id": str(ids[PARTICIPANT]),
                    "role": "user",
                    "content": "participant message",
                    "message_id": None,
                    "seq": 2,
                    "created_at": now,
                },
            ]
        )
    )
    harness.run(
        harness.db.execution_logs.insert_many(
            [
                {
                    "main_id": TENANT,
                    "session_id": str(session_oid),
                    "user_id": str(ids[OWNER]),
                    "message_id": "log-owner",
                },
                {
                    "main_id": TENANT,
                    "session_id": str(session_oid),
                    "user_id": str(ids[PARTICIPANT]),
                    "message_id": "log-participant",
                },
            ]
        )
    )
    # A rotated binding pair, exactly the shape rotation leaves behind
    # (runtime_coordinator.rotate_binding + the synchronizer's dispose of
    # the predecessor): the predecessor is superseded (current=False), the
    # successor is the conversation's current server binding.
    bindings = KernelBindingRepository(harness.db)
    harness.run(bindings.ensure_indexes())
    predecessor = harness.run(
        bindings.create(
            tenant_id=TENANT,
            user_id=str(ids[OWNER]),
            conversation_id=str(session_oid),
            kernel_session_id=f"ks-{session_oid}-a",
            runtime_id="rt-test",
            profile_version="pv-old",
            model_instance_id="mi-old",
            kernel_version="test-kernel",
        )
    )
    harness.run(
        bindings.create(
            tenant_id=TENANT,
            user_id=str(ids[OWNER]),
            conversation_id=str(session_oid),
            kernel_session_id=f"ks-{session_oid}-b",
            runtime_id="rt-test",
            profile_version="pv-new",
            model_instance_id="mi-new",
            kernel_version="test-kernel",
            replaces_binding_id=str(predecessor["binding_id"]),
        )
    )
    participants = SessionParticipantsRepository(harness.db)
    harness.run(
        participants.add(tenant_id=TENANT, conversation_id=str(session_oid), user_id=str(ids[PARTICIPANT]))
    )
    harness.run(
        participants.add(tenant_id=TENANT, conversation_id=str(session_oid), user_id=str(ids[REMOVED]))
    )
    harness.run(participants.remove(str(session_oid), tenant_id=TENANT, user_id=str(ids[REMOVED])))

    gateway = _FakeGateway()
    chat = DshChatService(
        gateway=gateway,
        coordinator=RuntimeCoordinator(gateway, KernelBindingRepository(harness.db)),
        conversations=ConversationRepository(harness.db),
        bindings=KernelBindingRepository(harness.db),
        events=KernelEventRepository(harness.db),
        profiles=_FakeProfiles(),
        kernel_version="test-kernel",
    )
    monkeypatch.setattr(dsh_runtime_application, "chat", chat)

    return harness, ids, session_oid, gateway


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _owner_delete(harness, session_oid: ObjectId, *, user_id: str):
    """Owner deletes the session through the REAL handler (all
    Query-defaulted params passed explicitly — T8's gotcha; the claimed
    user_id is the caller's OWN resolved id — T11's lesson)."""
    return harness.run(
        delete_session(
            str(session_oid),
            user_id=user_id,
            main_id=TENANT,
            main_id_snake=None,
            authorization=f"Bearer {TOKENS[OWNER]}",
        )
    )


# ---------------------------------------------------------------------------
# New behaviour (RED on the unchanged code — the cascade)
# ---------------------------------------------------------------------------


def test_owner_delete_removes_every_message_regardless_of_author(owned_thread):
    # QA happy (plan todo 12): after owner delete,
    # chat_messages.count({session_id}) == 0 including participant-authored
    # rows — the user_id filter comes OFF the delete_many call.
    harness, ids, session_oid, _ = owned_thread
    response = _owner_delete(harness, session_oid, user_id=str(ids["owner"]))

    assert response.code == 0
    remaining = harness.run(harness.db.chat_messages.count_documents({"session_id": session_oid}))
    assert remaining == 0


def test_owner_delete_removes_execution_logs_by_session_regardless_of_author(owned_thread):
    # QA happy (plan todo 12): execution_logs are removed by session_id
    # (keeping main_id) regardless of author.
    harness, ids, session_oid, _ = owned_thread
    response = _owner_delete(harness, session_oid, user_id=str(ids["owner"]))

    assert response.code == 0
    remaining = harness.run(
        harness.db.execution_logs.count_documents({"session_id": str(session_oid)})
    )
    assert remaining == 0


def test_owner_delete_disposes_every_binding_for_the_conversation(owned_thread):
    # QA happy (plan todo 12): zero current:true bindings remain and EVERY
    # binding row for the conversation is disposed — the superseded
    # predecessor too (belt-and-suspenders), and both kernel sessions are
    # disposed through the gateway.
    harness, ids, session_oid, gateway = owned_thread
    response = _owner_delete(harness, session_oid, user_id=str(ids["owner"]))

    assert response.code == 0

    async def _all_rows(cursor):
        return [row async for row in cursor]

    all_rows = harness.run(
        _all_rows(harness.db.agent_kernel_bindings.find({"conversation_id": str(session_oid)}))
    )
    assert len(all_rows) == 2
    assert [row["status"] for row in all_rows] == ["disposed", "disposed"]
    current_count = harness.run(
        harness.db.agent_kernel_bindings.count_documents(
            {"conversation_id": str(session_oid), "current": True}
        )
    )
    assert current_count == 0
    assert sorted(gateway.disposed_sessions) == sorted([f"ks-{session_oid}-a", f"ks-{session_oid}-b"])


def test_owner_delete_removes_all_session_participant_rows(owned_thread):
    # QA happy (plan todo 12): zero session_participants rows remain —
    # T2's delete_for_conversation hard-deletes active AND removed rows.
    harness, ids, session_oid, _ = owned_thread
    response = _owner_delete(harness, session_oid, user_id=str(ids["owner"]))

    assert response.code == 0
    remaining = harness.run(
        harness.db.session_participants.count_documents({"conversation_id": str(session_oid)})
    )
    assert remaining == 0


def test_participant_delete_attempt_leaves_every_artifact_intact(owned_thread):
    # QA failure (plan todo 12): a delete attempt by a participant leaves
    # every artifact intact. The 404 authorization gate (T11) precedes the
    # cascade, so dispose_conversation is never reached.
    harness, ids, session_oid, gateway = owned_thread
    with pytest.raises(HTTPException) as excinfo:
        harness.run(
            delete_session(
                str(session_oid),
                user_id=str(ids["participant"]),
                main_id=TENANT,
                main_id_snake=None,
                authorization=f"Bearer {TOKENS[PARTICIPANT]}",
            )
        )

    assert excinfo.value.status_code == 404
    doc = harness.run(harness.db.chat_sessions.find_one({"_id": session_oid}))
    assert doc is not None
    assert doc["title"] == "Shared chat"
    messages = harness.run(harness.db.chat_messages.count_documents({"session_id": session_oid}))
    assert messages == 2
    rows = harness.run(
        harness.db.session_participants.count_documents({"conversation_id": str(session_oid)})
    )
    assert rows == 2
    bindings = harness.run(
        harness.db.agent_kernel_bindings.count_documents(
            {"conversation_id": str(session_oid), "current": True}
        )
    )
    assert bindings == 1
    assert gateway.disposed_sessions == []


def test_append_messages_404_stays_coherent_after_owner_delete(owned_thread):
    # The append_messages 404 pre-check (sessions.py:1139-1143) must stay
    # coherent when the cascade starts deleting participant rows: after the
    # owner delete the deleted session's rows — participant rows included —
    # are gone, so a legacy append attempt gets the pre-check's clean 404,
    # never the 409 active-participant guard and never a 500.
    harness, ids, session_oid, _ = owned_thread
    deleted = _owner_delete(harness, session_oid, user_id=str(ids["owner"]))
    assert deleted.code == 0

    with pytest.raises(HTTPException) as excinfo:
        harness.run(
            sessions_module.append_messages(
                str(session_oid),
                MessageAppend(
                    user_id=str(ids["owner"]),
                    main_id=TENANT,
                    messages=[MessageIn(role="user", content="after delete")],
                ),
                authorization=f"Bearer {TOKENS[OWNER]}",
            )
        )

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Session not found"
    # And the participant row is gone with everything else — the pre-check
    # is not the only thing standing between the writer and an orphaned row.
    remaining = harness.run(
        harness.db.session_participants.count_documents({"conversation_id": str(session_oid)})
    )
    assert remaining == 0
