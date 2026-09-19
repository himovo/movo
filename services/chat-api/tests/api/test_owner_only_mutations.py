# allow: SIZE_OK — cohesive 8-test pinned matrix over the two owner-only mutation
# surfaces (frozen plan todo 11's QA matrix; T04/T07/T08/T09/T10 precedent).
"""Plan todo 11 — PATCH /sessions/{id} and DELETE /sessions/{id} are OWNER-only.

Both handlers scope their lookups by the authenticated ``user_id``
(``add_main_scope({"_id", "user_id"}, main_id)`` — the ``owned()``-equivalent
filter family), so a participant — active or removed — receives 404 (the
existence-disclosure rule: 404 cannot-see, never 403) and the session and every
artifact survive their attempt. These tests pin that contract on the REAL
handler code against a real mongod; every non-owner caller claims their OWN
user_id/main_id so the 404 comes from the ownership filter, not the
claimed-mismatch guard in ``_authorized_scope``.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from bson import ObjectId
from fastapi import HTTPException

from app.api.endpoints import sessions as sessions_module
from app.api.endpoints.sessions import SessionUpdate, delete_session, update_session
from app.dsh_runtime.application import dsh_runtime_application
from app.dsh_runtime.bindings.repository import KernelBindingRepository
from app.dsh_runtime.conversation.participants_repository import SessionParticipantsRepository

TENANT = "tenant-owner-only-mutations"
OTHER_TENANT = "tenant-somewhere-else"
ORIGINAL_TITLE = "Original title"


class _RecordingChatService:
    """Stand-in for the DshChatService singleton (never started in tests).

    The owner DELETE path calls ``dsh_runtime_application.require_chat()``
    before deleting; the dispose cascade itself is todo 12's surface, so T11
    only needs the endpoint's authorization to run past it for the owner.
    """

    def __init__(self) -> None:
        self.disposed: list[tuple[str, str, str]] = []

    async def dispose_conversation(self, conversation_id: str, *, tenant_id: str, user_id: str) -> None:
        self.disposed.append((conversation_id, tenant_id, user_id))


@pytest.fixture
def owned_thread(real_mongo_db, monkeypatch):
    """A clean owner thread with one active participant, one removed
    participant, one same-tenant non-member, one cross-tenant user, one
    message and one current server binding."""
    harness = real_mongo_db
    harness.run(SessionParticipantsRepository(harness.db).ensure_indexes())
    monkeypatch.setattr(sessions_module, "get_db", lambda: harness.db)

    ids = {
        "owner": ObjectId(),
        "participant": ObjectId(),
        "removed": ObjectId(),
        "nonmember": ObjectId(),
        "cross": ObjectId(),
    }
    directory = {
        "token-owner": {"user": {"_id": ids["owner"]}, "main_id": TENANT},
        "token-participant": {"user": {"_id": ids["participant"]}, "main_id": TENANT},
        "token-removed": {"user": {"_id": ids["removed"]}, "main_id": TENANT},
        "token-nonmember": {"user": {"_id": ids["nonmember"]}, "main_id": TENANT},
        "token-cross": {"user": {"_id": ids["cross"]}, "main_id": OTHER_TENANT},
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
                "user_id": str(ids["owner"]),
                "main_id": TENANT,
                "title": ORIGINAL_TITLE,
                "created_at": now,
                "updated_at": now,
            }
        )
    )
    harness.run(
        harness.db.chat_messages.insert_one(
            {
                "main_id": TENANT,
                "session_id": session_oid,
                "user_id": str(ids["owner"]),
                "role": "user",
                "content": "owner message",
                "message_id": None,
                "seq": 1,
                "created_at": now,
            }
        )
    )
    harness.run(
        KernelBindingRepository(harness.db).create(
            tenant_id=TENANT,
            user_id=str(ids["owner"]),
            conversation_id=str(session_oid),
            kernel_session_id=f"ks-{session_oid}",
            runtime_id="rt-test",
            profile_version="pv-test",
            model_instance_id="mi-test",
            kernel_version="0.1.0-rc.6",
        )
    )
    participants = SessionParticipantsRepository(harness.db)
    harness.run(
        participants.add(tenant_id=TENANT, conversation_id=str(session_oid), user_id=str(ids["participant"]))
    )
    harness.run(
        participants.add(tenant_id=TENANT, conversation_id=str(session_oid), user_id=str(ids["removed"]))
    )
    harness.run(
        participants.remove(str(session_oid), tenant_id=TENANT, user_id=str(ids["removed"]))
    )

    chat_stub = _RecordingChatService()
    monkeypatch.setattr(dsh_runtime_application, "chat", chat_stub)

    return harness, ids, session_oid


def test_owner_patch_succeeds(owned_thread):
    harness, ids, session_oid = owned_thread
    response = harness.run(
        update_session(
            str(session_oid),
            SessionUpdate(user_id=str(ids["owner"]), main_id=TENANT, title="Renamed by owner"),
            authorization="Bearer token-owner",
        )
    )
    assert response.code == 0
    assert response.data["title"] == "Renamed by owner"
    doc = harness.run(harness.db.chat_sessions.find_one({"_id": session_oid}))
    assert doc is not None
    assert doc["title"] == "Renamed by owner"


def test_owner_delete_succeeds(owned_thread):
    harness, ids, session_oid = owned_thread
    response = harness.run(
        delete_session(
            str(session_oid),
            user_id=str(ids["owner"]),
            main_id=TENANT,
            main_id_snake=None,
            authorization="Bearer token-owner",
        )
    )
    assert response.code == 0
    assert response.data == {"id": str(session_oid)}
    assert harness.run(harness.db.chat_sessions.find_one({"_id": session_oid})) is None


def test_participant_patch_receives_404(owned_thread):
    harness, ids, session_oid = owned_thread
    # The participant claims their OWN id (what the real client sends): the
    # 404 must come from the ownership filter, not the claimed-mismatch guard.
    with pytest.raises(HTTPException) as excinfo:
        harness.run(
            update_session(
                str(session_oid),
                SessionUpdate(user_id=str(ids["participant"]), main_id=TENANT, title="Renamed by participant"),
                authorization="Bearer token-participant",
            )
        )
    assert excinfo.value.status_code == 404
    doc = harness.run(harness.db.chat_sessions.find_one({"_id": session_oid}))
    assert doc is not None
    assert doc["title"] == ORIGINAL_TITLE


def test_participant_delete_receives_404_and_leaves_every_artifact_intact(owned_thread):
    harness, ids, session_oid = owned_thread
    with pytest.raises(HTTPException) as excinfo:
        harness.run(
            delete_session(
                str(session_oid),
                user_id=str(ids["participant"]),
                main_id=TENANT,
                main_id_snake=None,
                authorization="Bearer token-participant",
            )
        )
    assert excinfo.value.status_code == 404
    # The session still exists, untouched.
    doc = harness.run(harness.db.chat_sessions.find_one({"_id": session_oid}))
    assert doc is not None
    assert doc["title"] == ORIGINAL_TITLE
    # Every artifact intact: messages, participants, bindings.
    messages = harness.run(harness.db.chat_messages.count_documents({"session_id": session_oid}))
    assert messages == 1
    rows = harness.run(
        SessionParticipantsRepository(harness.db).list(str(session_oid), tenant_id=TENANT)
    )
    assert [row["user_id"] for row in rows] == [str(ids["participant"])]
    bindings = harness.run(
        harness.db[KernelBindingRepository.COLLECTION].count_documents(
            {"conversation_id": str(session_oid), "current": True}
        )
    )
    assert bindings == 1


def test_removed_participant_patch_receives_404(owned_thread):
    harness, ids, session_oid = owned_thread
    with pytest.raises(HTTPException) as excinfo:
        harness.run(
            update_session(
                str(session_oid),
                SessionUpdate(user_id=str(ids["removed"]), main_id=TENANT, title="Renamed by removed participant"),
                authorization="Bearer token-removed",
            )
        )
    assert excinfo.value.status_code == 404
    doc = harness.run(harness.db.chat_sessions.find_one({"_id": session_oid}))
    assert doc is not None
    assert doc["title"] == ORIGINAL_TITLE


def test_removed_participant_delete_receives_404_and_session_survives(owned_thread):
    harness, ids, session_oid = owned_thread
    with pytest.raises(HTTPException) as excinfo:
        harness.run(
            delete_session(
                str(session_oid),
                user_id=str(ids["removed"]),
                main_id=TENANT,
                main_id_snake=None,
                authorization="Bearer token-removed",
            )
        )
    assert excinfo.value.status_code == 404
    assert harness.run(harness.db.chat_sessions.find_one({"_id": session_oid})) is not None


def test_non_member_patch_receives_404(owned_thread):
    harness, ids, session_oid = owned_thread
    with pytest.raises(HTTPException) as excinfo:
        harness.run(
            update_session(
                str(session_oid),
                SessionUpdate(user_id=str(ids["nonmember"]), main_id=TENANT, title="Renamed by non-member"),
                authorization="Bearer token-nonmember",
            )
        )
    assert excinfo.value.status_code == 404
    doc = harness.run(harness.db.chat_sessions.find_one({"_id": session_oid}))
    assert doc is not None
    assert doc["title"] == ORIGINAL_TITLE


def test_cross_tenant_patch_receives_404(owned_thread):
    harness, ids, session_oid = owned_thread
    # The cross-tenant caller claims their OWN main_id: the 404 must come from
    # the tenant-scoped ownership filter, not the claimed-mismatch guard.
    with pytest.raises(HTTPException) as excinfo:
        harness.run(
            update_session(
                str(session_oid),
                SessionUpdate(user_id=str(ids["cross"]), main_id=OTHER_TENANT, title="Renamed cross-tenant"),
                authorization="Bearer token-cross",
            )
        )
    assert excinfo.value.status_code == 404
    doc = harness.run(harness.db.chat_sessions.find_one({"_id": session_oid}))
    assert doc is not None
    assert doc["title"] == ORIGINAL_TITLE
