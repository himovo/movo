"""Endpoint-level tests for the session-share API surface.

Status codes are pinned by the plan: 404 when the caller cannot see the
session (non-member, removed member, or cross-tenant), 403 when the caller
can see it but lacks the right, 409 for unshareable conversations (no
current binding or non-server execution location), 410 for expired or
revoked tokens.
"""

# allow: SIZE_OK — cohesive 22-test matrix over one API surface; the frozen
# plan pins this single test file (plan todos 4 and 5).

from __future__ import annotations

import datetime
import json
import uuid
from typing import Any

import pytest
from bson import ObjectId
from fastapi import HTTPException

from app.api.endpoints import session_shares
from app.api.principal import ApiPrincipal
from app.dsh_runtime.bindings.repository import KernelBindingRepository
from app.dsh_runtime.conversation.participants_repository import SessionParticipantsRepository
from app.services import session_identity_projection as identity_projection
from app.services.session_sharing.service import hash_token, issue_share


TENANT = "tenant-a"
OTHER_TENANT = "tenant-b"


def _principal(main_id: str, user_id: str) -> ApiPrincipal:
    return ApiPrincipal(kind="end_user", main_id=main_id, user_id=user_id)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


async def _seed_user(db: Any, *, tenant_id: str, name: str) -> str:
    user_id = ObjectId()
    await db.end_users.insert_one({"_id": user_id, "main_id": tenant_id, "name": name, "status": "active"})
    return str(user_id)


async def _seed_session(db: Any, *, tenant_id: str, owner_id: str) -> str:
    now = _now()
    result = await db.chat_sessions.insert_one({
        "user_id": owner_id,
        "main_id": tenant_id,
        "title": "Shared session",
        "created_at": now,
        "updated_at": now,
    })
    return str(result.inserted_id)


async def _seed_server_binding(
    db: Any, *, tenant_id: str, owner_id: str, session_id: str, execution_location: str = "server",
) -> None:
    await KernelBindingRepository(db).create(
        tenant_id=tenant_id,
        user_id=owner_id,
        conversation_id=session_id,
        kernel_session_id=f"ks-{uuid.uuid4()}",
        runtime_id=f"rt-{uuid.uuid4()}",
        profile_version=f"pv-{uuid.uuid4()}",
        model_instance_id="model-instance",
        kernel_version="1",
        execution_location=execution_location,
    )


async def _seed_live_share(db: Any, *, session_id: str, expires_at: datetime.datetime) -> str:
    issued = issue_share({}, now=_now())
    await db.chat_sessions.update_one(
        {"_id": ObjectId(session_id)},
        {"$set": {
            "share_token_hash": issued["fields"]["share_token_hash"],
            "share_expires_at": expires_at,
            "share_revoked_at": None,
        }},
    )
    return issued["token"]


@pytest.fixture
def api_db(real_mongo_db, monkeypatch):
    harness = real_mongo_db
    monkeypatch.setattr(session_shares, "get_db", lambda: harness.db)
    harness.run(SessionParticipantsRepository(harness.db).ensure_indexes())
    return harness


def _create(harness: Any, session_id: str, principal: ApiPrincipal) -> dict[str, Any]:
    return harness.run(session_shares.create_session_share(
        session_id,
        session_shares.CreateShareRequest(expiresInDays=30),
        principal=principal,
    ))


# --- happy path -----------------------------------------------------------


def test_owner_creates_share_returns_token_once_with_expiry_and_count(api_db) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id))
    harness.run(_seed_server_binding(
        harness.db, tenant_id=TENANT, owner_id=owner_id, session_id=session_id))

    response = _create(harness, session_id, _principal(TENANT, owner_id))

    data = response["data"]
    assert isinstance(data["token"], str) and data["token"]
    assert data["expires_at"] > _now()
    assert data["participant_count"] == 0
    doc = harness.run(harness.db.chat_sessions.find_one({"_id": ObjectId(session_id)}))
    assert doc["share_token_hash"] == hash_token(data["token"])
    assert "token" not in doc


def test_second_tenant_user_joins_and_members_list_shows_both(api_db) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Alice Owner"))
    member_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Bob Member"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id))
    harness.run(_seed_server_binding(
        harness.db, tenant_id=TENANT, owner_id=owner_id, session_id=session_id))
    created = _create(harness, session_id, _principal(TENANT, owner_id))

    joined = harness.run(session_shares.join_session_share(
        created["data"]["token"], principal=_principal(TENANT, member_id)))

    assert joined["data"]["session_id"] == session_id
    listing = harness.run(session_shares.list_participants(
        session_id, principal=_principal(TENANT, member_id)))
    items = listing["data"]["items"]
    assert [(item["user_id"], item["role"]) for item in items] == [
        (owner_id, "owner"),
        (member_id, "participant"),
    ]
    assert [item["display_name"] for item in items] == ["Alice Owner", "Bob Member"]
    assert items[0]["joined_at"] is not None
    assert items[1]["joined_at"] is not None


def test_leave_removes_access(api_db) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    member_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Member"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id))
    harness.run(_seed_server_binding(
        harness.db, tenant_id=TENANT, owner_id=owner_id, session_id=session_id))
    created = _create(harness, session_id, _principal(TENANT, owner_id))
    harness.run(session_shares.join_session_share(
        created["data"]["token"], principal=_principal(TENANT, member_id)))

    left = harness.run(session_shares.leave_session(
        session_id, principal=_principal(TENANT, member_id)))

    assert left["data"]["session_id"] == session_id
    with pytest.raises(HTTPException) as exc_info:
        harness.run(session_shares.list_participants(
            session_id, principal=_principal(TENANT, member_id)))
    assert exc_info.value.status_code == 404
    listing = harness.run(session_shares.list_participants(
        session_id, principal=_principal(TENANT, owner_id)))
    assert [item["user_id"] for item in listing["data"]["items"]] == [owner_id]


def test_share_create_rotates_token_and_invalidates_previous(api_db) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    member_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Member"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id))
    harness.run(_seed_server_binding(
        harness.db, tenant_id=TENANT, owner_id=owner_id, session_id=session_id))
    first = _create(harness, session_id, _principal(TENANT, owner_id))

    second = _create(harness, session_id, _principal(TENANT, owner_id))

    assert second["data"]["token"] != first["data"]["token"]
    with pytest.raises(HTTPException) as exc_info:
        harness.run(session_shares.join_session_share(
            first["data"]["token"], principal=_principal(TENANT, member_id)))
    assert exc_info.value.status_code == 404
    joined = harness.run(session_shares.join_session_share(
        second["data"]["token"], principal=_principal(TENANT, member_id)))
    assert joined["data"]["session_id"] == session_id
    doc = harness.run(harness.db.chat_sessions.find_one({"_id": ObjectId(session_id)}))
    assert doc["share_revoked_at"] is None


def test_participant_count_counts_active_non_owner_rows(api_db) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    member_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Member"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id))
    harness.run(_seed_server_binding(
        harness.db, tenant_id=TENANT, owner_id=owner_id, session_id=session_id))

    created = _create(harness, session_id, _principal(TENANT, owner_id))
    assert created["data"]["participant_count"] == 0
    harness.run(session_shares.join_session_share(
        created["data"]["token"], principal=_principal(TENANT, member_id)))
    recreated = _create(harness, session_id, _principal(TENANT, owner_id))
    assert recreated["data"]["participant_count"] == 1


def test_owner_join_via_own_token_does_not_create_participant_row(api_db) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id))
    harness.run(_seed_server_binding(
        harness.db, tenant_id=TENANT, owner_id=owner_id, session_id=session_id))
    created = _create(harness, session_id, _principal(TENANT, owner_id))

    joined = harness.run(session_shares.join_session_share(
        created["data"]["token"], principal=_principal(TENANT, owner_id)))

    assert joined["data"]["session_id"] == session_id
    rows = harness.run(SessionParticipantsRepository(harness.db).list(
        session_id, tenant_id=TENANT))
    assert rows == []


# --- pinned failure matrix -------------------------------------------------


def test_non_member_create_share_rejected_404(api_db) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    outsider_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Outsider"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id))

    with pytest.raises(HTTPException) as exc_info:
        _create(harness, session_id, _principal(TENANT, outsider_id))

    assert exc_info.value.status_code == 404


def test_participant_create_share_rejected_403(api_db) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    member_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Member"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id))
    harness.run(SessionParticipantsRepository(harness.db).add(
        tenant_id=TENANT, conversation_id=session_id, user_id=member_id))

    with pytest.raises(HTTPException) as exc_info:
        _create(harness, session_id, _principal(TENANT, member_id))

    assert exc_info.value.status_code == 403


def test_cross_tenant_join_rejected_404(api_db) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id))
    token = harness.run(_seed_live_share(
        harness.db, session_id=session_id, expires_at=_now() + datetime.timedelta(days=1)))

    with pytest.raises(HTTPException) as exc_info:
        harness.run(session_shares.join_session_share(
            token, principal=_principal(OTHER_TENANT, "user-b")))

    assert exc_info.value.status_code == 404


def test_expired_token_join_rejected_410(api_db) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id))
    token = harness.run(_seed_live_share(
        harness.db, session_id=session_id, expires_at=_now() - datetime.timedelta(days=1)))

    with pytest.raises(HTTPException) as exc_info:
        harness.run(session_shares.join_session_share(
            token, principal=_principal(TENANT, "user-x")))

    assert exc_info.value.status_code == 410


def test_revoked_token_join_rejected_410(api_db) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id))
    token = harness.run(_seed_live_share(
        harness.db, session_id=session_id, expires_at=_now() + datetime.timedelta(days=1)))
    harness.run(harness.db.chat_sessions.update_one(
        {"_id": ObjectId(session_id)}, {"$set": {"share_revoked_at": _now()}}))

    with pytest.raises(HTTPException) as exc_info:
        harness.run(session_shares.join_session_share(
            token, principal=_principal(TENANT, "user-x")))

    assert exc_info.value.status_code == 410


def test_non_owner_remove_participant_rejected_403(api_db) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    member_a = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Member A"))
    member_b = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Member B"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id))
    participants = SessionParticipantsRepository(harness.db)
    harness.run(participants.add(tenant_id=TENANT, conversation_id=session_id, user_id=member_a))
    harness.run(participants.add(tenant_id=TENANT, conversation_id=session_id, user_id=member_b))

    with pytest.raises(HTTPException) as exc_info:
        harness.run(session_shares.remove_participant(
            session_id, member_b, principal=_principal(TENANT, member_a)))

    assert exc_info.value.status_code == 403


def test_join_twice_yields_one_row(api_db) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    member_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Member"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id))
    harness.run(_seed_server_binding(
        harness.db, tenant_id=TENANT, owner_id=owner_id, session_id=session_id))
    created = _create(harness, session_id, _principal(TENANT, owner_id))

    harness.run(session_shares.join_session_share(
        created["data"]["token"], principal=_principal(TENANT, member_id)))
    harness.run(session_shares.join_session_share(
        created["data"]["token"], principal=_principal(TENANT, member_id)))

    rows = harness.run(SessionParticipantsRepository(harness.db).list(
        session_id, tenant_id=TENANT))
    assert len(rows) == 1
    assert str(rows[0]["user_id"]) == member_id


def test_share_without_binding_rejected_409(api_db) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id))

    with pytest.raises(HTTPException) as exc_info:
        _create(harness, session_id, _principal(TENANT, owner_id))

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "session_share_no_binding"
    doc = harness.run(harness.db.chat_sessions.find_one({"_id": ObjectId(session_id)}))
    assert doc.get("share_token_hash") is None


def test_desktop_bound_session_share_rejected_409(api_db) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id))
    harness.run(_seed_server_binding(
        harness.db, tenant_id=TENANT, owner_id=owner_id, session_id=session_id,
        execution_location="desktop"))

    with pytest.raises(HTTPException) as exc_info:
        _create(harness, session_id, _principal(TENANT, owner_id))

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "session_share_not_server"


def test_removed_participant_members_list_rejected_404(api_db) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    member_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Member"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id))
    harness.run(SessionParticipantsRepository(harness.db).add(
        tenant_id=TENANT, conversation_id=session_id, user_id=member_id))
    harness.run(session_shares.remove_participant(
        session_id, member_id, principal=_principal(TENANT, owner_id)))

    with pytest.raises(HTTPException) as exc_info:
        harness.run(session_shares.list_participants(
            session_id, principal=_principal(TENANT, member_id)))

    assert exc_info.value.status_code == 404


# --- verbatim acceptance regressions ---------------------------------------


def test_revoke_clears_hash_and_keeps_participants(api_db) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    member_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Member"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id))
    harness.run(_seed_server_binding(
        harness.db, tenant_id=TENANT, owner_id=owner_id, session_id=session_id))
    created = _create(harness, session_id, _principal(TENANT, owner_id))
    harness.run(session_shares.join_session_share(
        created["data"]["token"], principal=_principal(TENANT, member_id)))

    revoked = harness.run(session_shares.revoke_session_share(
        session_id, principal=_principal(TENANT, owner_id)))

    assert revoked["data"]["session_id"] == session_id
    doc = harness.run(harness.db.chat_sessions.find_one({"_id": ObjectId(session_id)}))
    assert doc["share_revoked_at"] is not None
    assert doc["share_token_hash"] is None
    rows = harness.run(SessionParticipantsRepository(harness.db).list(
        session_id, tenant_id=TENANT))
    assert [str(row["user_id"]) for row in rows] == [member_id]
    with pytest.raises(HTTPException) as exc_info:
        harness.run(session_shares.join_session_share(
            created["data"]["token"], principal=_principal(TENANT, member_id)))
    assert exc_info.value.status_code == 404


def test_owner_cannot_leave_own_session(api_db) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id))

    with pytest.raises(HTTPException) as exc_info:
        harness.run(session_shares.leave_session(
            session_id, principal=_principal(TENANT, owner_id)))

    assert exc_info.value.status_code == 403


def test_blank_token_join_rejected_400(api_db) -> None:
    harness = api_db

    with pytest.raises(HTTPException) as exc_info:
        harness.run(session_shares.join_session_share("", principal=_principal(TENANT, "user-a")))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "session_share_token_required"


def test_unknown_token_join_rejected_404(api_db) -> None:
    harness = api_db

    with pytest.raises(HTTPException) as exc_info:
        harness.run(session_shares.join_session_share(
            "unknown-token-value", principal=_principal(TENANT, "user-a")))

    assert exc_info.value.status_code == 404


def test_malformed_session_id_rejected_404(api_db) -> None:
    harness = api_db

    with pytest.raises(HTTPException) as exc_info:
        _create(harness, "not-an-objectid", _principal(TENANT, "user-a"))

    assert exc_info.value.status_code == 404


# --- full lifecycle (plan todo 5 acceptance) --------------------------------


def test_full_share_token_lifecycle_end_to_end(api_db) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    member_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Member"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id))
    harness.run(_seed_server_binding(
        harness.db, tenant_id=TENANT, owner_id=owner_id, session_id=session_id))

    # create (owner)
    created = _create(harness, session_id, _principal(TENANT, owner_id))
    token = created["data"]["token"]
    assert token

    # join (second user)
    joined = harness.run(session_shares.join_session_share(
        token, principal=_principal(TENANT, member_id)))
    assert joined["data"]["session_id"] == session_id

    # read members (both viewers)
    for viewer in (owner_id, member_id):
        listing = harness.run(session_shares.list_participants(
            session_id, principal=_principal(TENANT, viewer)))
        assert [(item["user_id"], item["role"]) for item in listing["data"]["items"]] == [
            (owner_id, "owner"),
            (member_id, "participant"),
        ]

    # revoke (owner) — the endpoint clears share_token_hash, so the revoked
    # token resolves 404 (unknown) on the next join (T04-failure semantics).
    revoked = harness.run(session_shares.revoke_session_share(
        session_id, principal=_principal(TENANT, owner_id)))
    assert revoked["data"]["session_id"] == session_id

    # join-again-rejected: the revoked-via-endpoint token -> 404 (hash cleared);
    # a seeded hash-intact revoked session -> 410 (the fail-closed branch).
    with pytest.raises(HTTPException) as exc_info:
        harness.run(session_shares.join_session_share(
            token, principal=_principal(TENANT, member_id)))
    assert exc_info.value.status_code == 404

    stale_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id))
    stale_token = harness.run(_seed_live_share(
        harness.db, session_id=stale_id, expires_at=_now() + datetime.timedelta(days=1)))
    harness.run(harness.db.chat_sessions.update_one(
        {"_id": ObjectId(stale_id)}, {"$set": {"share_revoked_at": _now()}}))
    with pytest.raises(HTTPException) as exc_info:
        harness.run(session_shares.join_session_share(
            stale_token, principal=_principal(TENANT, member_id)))
    assert exc_info.value.status_code == 410

    # regenerate (owner creates a new link) — clears share_revoked_at
    regenerated = _create(harness, session_id, _principal(TENANT, owner_id))
    new_token = regenerated["data"]["token"]
    assert new_token != token
    doc = harness.run(harness.db.chat_sessions.find_one({"_id": ObjectId(session_id)}))
    assert doc["share_revoked_at"] is None
    assert doc["share_token_hash"] == hash_token(new_token)

    # new token works and old tokens fail
    rejoined = harness.run(session_shares.join_session_share(
        new_token, principal=_principal(TENANT, member_id)))
    assert rejoined["data"]["session_id"] == session_id
    rows = harness.run(SessionParticipantsRepository(harness.db).list(
        session_id, tenant_id=TENANT))
    assert [str(row["user_id"]) for row in rows] == [member_id]
    with pytest.raises(HTTPException) as exc_info:
        harness.run(session_shares.join_session_share(
            token, principal=_principal(TENANT, member_id)))
    assert exc_info.value.status_code == 404
    with pytest.raises(HTTPException) as exc_info:
        harness.run(session_shares.join_session_share(
            stale_token, principal=_principal(TENANT, member_id)))
    assert exc_info.value.status_code == 410


# --- todo 5: participant identity projection + avatar grammar -----------------


class _FakeStorage:
    def sign_url(self, object_path: str) -> str:
        return f"https://signed.example.com/{object_path.rsplit('/', 1)[-1]}?sig=test"


class _BrokenStorage:
    def sign_url(self, object_path: str) -> str:
        raise RuntimeError("signing unavailable")


async def _seed_user_profile(
    db: Any,
    *,
    tenant_id: str,
    name: str,
    avatar: str | None = None,
    avatar_object_path: str | None = None,
) -> str:
    user_id = ObjectId()
    document: dict[str, Any] = {
        "_id": user_id, "main_id": tenant_id, "name": name, "status": "active",
    }
    if avatar is not None:
        document["avatar"] = avatar
    if avatar_object_path is not None:
        document["avatar_object_path"] = avatar_object_path
    await db.end_users.insert_one(document)
    return str(user_id)


def _listing_items(harness: Any, session_id: str, viewer_id: str) -> list[dict[str, Any]]:
    listing = harness.run(session_shares.list_participants(
        session_id, principal=_principal(TENANT, viewer_id)))
    return listing["data"]["items"]


def test_participant_listing_projects_identity_and_signed_avatars(api_db, monkeypatch) -> None:
    monkeypatch.setattr(identity_projection, "ObjectStorageClient", _FakeStorage)
    harness = api_db
    owner_id = harness.run(_seed_user_profile(
        harness.db, tenant_id=TENANT, name="Alice Owner",
        avatar="https://cdn.example.com/owner.png",
    ))
    direct_id = harness.run(_seed_user_profile(
        harness.db, tenant_id=TENANT, name="Bob Direct", avatar="/static/bob.png",
    ))
    path_id = harness.run(_seed_user_profile(
        harness.db, tenant_id=TENANT, name="Carol Path",
        avatar_object_path="tenants/a/carol.png",
    ))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id))
    for member_id in (direct_id, path_id):
        harness.run(SessionParticipantsRepository(harness.db).add(
            tenant_id=TENANT, conversation_id=session_id, user_id=member_id))

    items = _listing_items(harness, session_id, owner_id)

    assert [
        (item["user_id"], item["display_name"], item["role"], item["avatar_url"])
        for item in items
    ] == [
        (owner_id, "Alice Owner", "owner", "https://cdn.example.com/owner.png"),
        (direct_id, "Bob Direct", "participant", "/static/bob.png"),
        (path_id, "Carol Path", "participant", "https://signed.example.com/carol.png?sig=test"),
    ]
    payload = json.dumps(items, default=str)
    assert "avatar_object_path" not in payload
    assert "tenants/a/carol.png" not in payload


def test_participant_listing_avatar_grammar_rejects_unsafe_values(api_db) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user_profile(
        harness.db, tenant_id=TENANT, name="Owner", avatar="//evil.example.com/x.png",
    ))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id))
    unsafe_avatars = [
        "javascript:alert(1)",
        "data:image/png;base64,AAAA",
        "http://user:pass@cdn.example.com/x.png",
        "https://cdn.example.com/back\\slash.png",
        "\\\\host\\share\\x.png",
        "bad\x01control",
        "ftp://cdn.example.com/x.png",
    ]
    unsafe_ids: dict[str, str] = {}
    for index, avatar in enumerate(unsafe_avatars):
        user_id = harness.run(_seed_user_profile(
            harness.db, tenant_id=TENANT, name=f"Unsafe {index}", avatar=avatar,
        ))
        unsafe_ids[avatar] = user_id
        harness.run(SessionParticipantsRepository(harness.db).add(
            tenant_id=TENANT, conversation_id=session_id, user_id=user_id))
    safe_id = harness.run(_seed_user_profile(
        harness.db, tenant_id=TENANT, name="Safe Rel", avatar="/ok/relative.png",
    ))
    harness.run(SessionParticipantsRepository(harness.db).add(
        tenant_id=TENANT, conversation_id=session_id, user_id=safe_id))
    ghost_id = str(ObjectId())
    harness.run(SessionParticipantsRepository(harness.db).add(
        tenant_id=TENANT, conversation_id=session_id, user_id=ghost_id))

    by_id = {item["user_id"]: item for item in _listing_items(harness, session_id, owner_id)}

    for avatar, user_id in unsafe_ids.items():
        assert by_id[user_id]["avatar_url"] is None, avatar
    assert by_id[owner_id]["avatar_url"] is None
    assert by_id[safe_id]["avatar_url"] == "/ok/relative.png"
    # A participant whose end_users row is missing degrades, never 5xx.
    assert by_id[ghost_id]["display_name"] == ""
    assert by_id[ghost_id]["avatar_url"] is None


def test_participant_listing_signing_failure_returns_null_never_object_path(api_db, monkeypatch) -> None:
    monkeypatch.setattr(identity_projection, "ObjectStorageClient", _BrokenStorage)
    harness = api_db
    owner_id = harness.run(_seed_user_profile(
        harness.db, tenant_id=TENANT, name="Owner",
        avatar_object_path="private/tenant/owner.png",
    ))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id))

    items = _listing_items(harness, session_id, owner_id)

    assert items[0]["display_name"] == "Owner"
    assert items[0]["avatar_url"] is None
    payload = json.dumps(items, default=str)
    assert "private/tenant/owner.png" not in payload
    assert "avatar_object_path" not in payload


def test_participant_listing_cross_tenant_user_is_not_resolved(api_db) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    foreign_id = harness.run(_seed_user(harness.db, tenant_id=OTHER_TENANT, name="Tenant B Member"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id))
    harness.run(SessionParticipantsRepository(harness.db).add(
        tenant_id=TENANT, conversation_id=session_id, user_id=foreign_id))

    by_id = {item["user_id"]: item for item in _listing_items(harness, session_id, owner_id)}

    assert by_id[foreign_id]["display_name"] == ""
    assert by_id[foreign_id]["avatar_url"] is None
    assert "Tenant B Member" not in json.dumps(
        _listing_items(harness, session_id, owner_id), default=str)
