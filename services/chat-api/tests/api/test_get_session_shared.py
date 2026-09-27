"""Endpoint-level tests for ``GET /sessions/{session_id}`` (plan todo 9).

Pinned contract:

- The endpoint authorises the viewer as owner-or-ACTIVE-participant (T4's
  pinned pattern: owner = the session doc's ``user_id``; participant = an
  active ``session_participants`` row). A non-member, a removed participant
  and a cross-tenant caller all receive 404 — never 403 — to avoid existence
  disclosure.
- The message read is session-scoped (T6's ``list_messages``: by
  ``(main_id, session_id)`` served by the unique ``unique_main_session_seq``
  index, ``seq`` ascending) — the old viewer-scoped ``user_id`` filter is gone
  from the read path, so every member reads the full thread.
- Each returned message carries its author in ``user_id`` (a server-side
  addition to the serialisation).
- The detail response carries the access fields (``access`` ``"owner" |``
  ``"shared"``, ``owner_user_id``, ``participant_count``) — the pinned T09
  decision: SessionDetail captures what ``_serialize_session`` emits instead
  of silently dropping it (pydantic ``extra='ignore'``), while SessionSummary
  stays without them so the owner list payload (T8's byte-compatible
  contract) is unchanged.
- Owner-only behaviour preserved: a participant's GET does not clear the
  owner's ``scheduled_unread``; context-summary rows stay excluded unless
  ``includeContextSummary`` is set.

TDD phases: baseline characterization (4 passed on the UNCHANGED code —
owner-only reads via the ``user_id`` filter, viewer-scoped message query,
per-message ``user_id`` absent, non-member 404, invalid id 400) -> RED (the
participant/detail tests below fail on the unchanged code) -> GREEN. The
owner-only-query and user_id-absent pins are superseded by this todo's new
contract; the status-only pins survive.
"""

# allow: SIZE_OK — cohesive 11-test pinned matrix over one API surface
# (characterization + the todo-9 QA matrix); T04/T08 precedent for
# session-sharing endpoint test files.

from __future__ import annotations

import asyncio
import datetime
import json
from typing import Any

import pytest
from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from app.api.endpoints import sessions
from app.dsh_runtime.conversation.participants_repository import SessionParticipantsRepository
from app.dsh_runtime.conversation.repository import ConversationRepository
from app.dsh_runtime.session_live import parse_live_cursor
from app.services import session_identity_projection as identity_projection


TENANT = "tenant-a"


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _at(seconds_offset: int) -> datetime.datetime:
    return _now() + datetime.timedelta(seconds=seconds_offset)


async def _seed_user(db: Any, *, tenant_id: str, name: str) -> str:
    user_id = ObjectId()
    await db.end_users.insert_one({"_id": user_id, "main_id": tenant_id, "name": name, "status": "active"})
    return str(user_id)


async def _seed_session(
    db: Any,
    *,
    tenant_id: str,
    owner_id: str,
    updated_at: datetime.datetime | None = None,
    title: str = "A session",
    scheduled_unread: bool = False,
    next_message_seq: int | None = None,
    active_run: dict[str, Any] | None = None,
) -> str:
    now = updated_at or _now()
    document: dict[str, Any] = {
        "user_id": owner_id,
        "main_id": tenant_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "scheduled_unread": scheduled_unread,
    }
    if next_message_seq is not None:
        document["next_message_seq"] = next_message_seq
    if active_run is not None:
        document["active_run"] = active_run
    result = await db.chat_sessions.insert_one(document)
    return str(result.inserted_id)


async def _seed_message(
    db: Any,
    *,
    session_id: str,
    user_id: str,
    tenant_id: str,
    seq: int,
    content: str,
    role: str = "user",
    message_type: str = "normal",
    message_id: str | None = None,
    created_at: datetime.datetime | None = None,
) -> str:
    result = await db.chat_messages.insert_one({
        "session_id": ObjectId(session_id),
        "user_id": user_id,
        "main_id": tenant_id,
        "role": role,
        "content": content,
        "created_at": created_at or _at(-100),
        "seq": seq,
        "message_type": message_type,
        "message_id": message_id,
    })
    return str(result.inserted_id)


async def _seed_unsequenced_message(
    db: Any,
    *,
    session_id: str,
    user_id: str,
    tenant_id: str,
    content: str,
    role: str = "user",
    message_id: str | None = None,
    created_at: datetime.datetime | None = None,
) -> str:
    document: dict[str, Any] = {
        "session_id": ObjectId(session_id),
        "user_id": user_id,
        "main_id": tenant_id,
        "role": role,
        "content": content,
        "created_at": created_at or _at(-100),
        "message_type": "normal",
    }
    if message_id is not None:
        document["message_id"] = message_id
    result = await db.chat_messages.insert_one(document)
    return str(result.inserted_id)


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


async def _join(db: Any, *, tenant_id: str, session_id: str, user_id: str) -> None:
    await SessionParticipantsRepository(db).add(
        tenant_id=tenant_id, conversation_id=session_id, user_id=user_id
    )


@pytest.fixture
def api_db(real_mongo_db, monkeypatch):
    harness = real_mongo_db
    monkeypatch.setattr(sessions, "get_db", lambda: harness.db)
    harness.run(SessionParticipantsRepository(harness.db).ensure_indexes())
    # The session-scoped message read is served by the unique per-session
    # sequence index (created by ConversationRepository.ensure_indexes() in
    # production, app/dsh_runtime/conversation/repository.py) — the fixture
    # mirrors the production requirement without executing that module.
    harness.run(harness.db.chat_messages.create_index(
        [("main_id", 1), ("session_id", 1), ("seq", 1)],
        unique=True,
        name="unique_main_session_seq",
    ))
    return harness


class _CaptureCollection:
    def __init__(self, collection: Any, captured: dict[str, Any], name: str) -> None:
        self._collection = collection
        self._captured = captured
        self._name = name

    def __getattr__(self, name: str) -> Any:
        return getattr(self._collection, name)

    def find_one(self, *args: Any, **kwargs: Any) -> Any:
        self._captured.setdefault(self._name, {})["find_one"] = args[0] if args else None
        return self._collection.find_one(*args, **kwargs)

    def find(self, *args: Any, **kwargs: Any) -> Any:
        self._captured.setdefault(self._name, {})["find"] = args[0] if args else None
        return self._collection.find(*args, **kwargs)


class _CaptureDb:
    def __init__(self, db: Any, names: tuple[str, ...]) -> None:
        self._db = db
        self.captured: dict[str, Any] = {}
        for name in names:
            setattr(self, name, _CaptureCollection(getattr(db, name), self.captured, name))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._db, name)


def _get(
    harness: Any,
    monkeypatch: Any,
    *,
    session_id: str,
    user_id: str,
    tenant_id: str = TENANT,
    include_context_summary: bool = False,
) -> Any:
    # The endpoint resolves the viewer from the authorization header; patch the
    # module-level seam (T8's pattern) so each test drives the handler directly
    # as a specific seeded viewer. Every Query-defaulted parameter is passed
    # explicitly — a handler called outside FastAPI keeps the raw Query(...)
    # default objects, which are truthy.
    async def _fake_resolve(authorization: str | None) -> dict[str, Any]:
        return {"user": {"_id": ObjectId(user_id)}, "main_id": tenant_id}

    monkeypatch.setattr(sessions, "_resolve_session_user", _fake_resolve)
    return harness.run(sessions.get_session(
        session_id=session_id,
        user_id=user_id,
        main_id=tenant_id,
        main_id_snake=None,
        include_context_summary=include_context_summary,
        authorization=None,
    ))


# --- the shared-thread read (RED until implemented) ---


def test_participant_get_returns_full_thread_in_seq_order_with_authors(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    viewer_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Participant"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id, title="Joined"))
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=session_id, user_id=viewer_id))
    harness.run(_seed_message(
        harness.db, session_id=session_id, user_id=owner_id, tenant_id=TENANT,
        seq=1, content="owner first", role="user",
    ))
    harness.run(_seed_message(
        harness.db, session_id=session_id, user_id=owner_id, tenant_id=TENANT,
        seq=2, content="owner second", role="assistant",
    ))
    harness.run(_seed_message(
        harness.db, session_id=session_id, user_id=viewer_id, tenant_id=TENANT,
        seq=3, content="participant reply", role="user",
    ))

    response = _get(harness, monkeypatch, session_id=session_id, user_id=viewer_id)

    # Every message including the owner's, in seq order, each with its author.
    messages = response.data["messages"]
    assert [(m["content"], m["user_id"]) for m in messages] == [
        ("owner first", owner_id),
        ("owner second", owner_id),
        ("participant reply", viewer_id),
    ]
    # Pinned T09 detail contract for a shared session (the viewer's access).
    assert response.data["access"] == "shared"
    assert response.data["owner_user_id"] == owner_id
    assert response.data["user_id"] == owner_id  # session doc's user_id remains the owner
    assert response.data["participant_count"] == 1  # the viewer's active non-owner row
    assert response.data["id"] == session_id
    assert response.data["main_id"] == TENANT


def test_participant_get_message_query_is_session_scoped(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    viewer_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Participant"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id, title="Joined"))
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=session_id, user_id=viewer_id))
    harness.run(_seed_message(
        harness.db, session_id=session_id, user_id=owner_id, tenant_id=TENANT,
        seq=1, content="owner first", role="user",
    ))

    proxy_db = _CaptureDb(harness.db, ("chat_sessions", "chat_messages"))
    monkeypatch.setattr(sessions, "get_db", lambda: proxy_db)
    response = _get(harness, monkeypatch, session_id=session_id, user_id=viewer_id)

    # Session lookup: membership authorization — no user_id filter.
    session_filter = proxy_db.captured["chat_sessions"]["find_one"]
    assert session_filter["_id"] == ObjectId(session_id)
    assert session_filter["main_id"] == TENANT
    assert "user_id" not in session_filter
    # Message read: session-scoped (main_id, session_id) — the viewer's
    # user_id filter is gone from the read path.
    message_filter = proxy_db.captured["chat_messages"]["find"]
    assert message_filter["main_id"] == TENANT
    assert message_filter["session_id"] == ObjectId(session_id)
    assert "user_id" not in message_filter
    assert [m["content"] for m in response.data["messages"]] == ["owner first"]


def test_owner_get_sees_full_thread_including_participant_authored_rows(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    viewer_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Participant"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id, title="Joined"))
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=session_id, user_id=viewer_id))
    harness.run(_seed_message(
        harness.db, session_id=session_id, user_id=owner_id, tenant_id=TENANT,
        seq=1, content="owner first", role="user",
    ))
    harness.run(_seed_message(
        harness.db, session_id=session_id, user_id=viewer_id, tenant_id=TENANT,
        seq=2, content="participant reply", role="user",
    ))

    response = _get(harness, monkeypatch, session_id=session_id, user_id=owner_id)

    # The de-scoped read does not narrow the owner's view: both authors'
    # rows, attributed, in seq order.
    messages = response.data["messages"]
    assert [(m["content"], m["user_id"]) for m in messages] == [
        ("owner first", owner_id),
        ("participant reply", viewer_id),
    ]
    # Pinned T09 detail contract for an owned session.
    assert response.data["access"] == "owner"
    assert response.data["owner_user_id"] == owner_id
    assert response.data["participant_count"] == 1  # the participant's active row


def test_owner_get_returns_detail_with_access_owner_and_zero_participant_count(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id, title="Mine"))
    harness.run(_seed_message(
        harness.db, session_id=session_id, user_id=owner_id, tenant_id=TENANT,
        seq=1, content="owner first", role="user",
    ))

    response = _get(harness, monkeypatch, session_id=session_id, user_id=owner_id)

    assert response.data["access"] == "owner"
    assert response.data["owner_user_id"] == owner_id
    assert response.data["participant_count"] == 0  # no participants joined
    assert response.data["user_id"] == owner_id
    assert len(response.data["messages"]) == 1


def test_participant_get_excludes_context_summary_rows_unless_requested(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    viewer_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Participant"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id, title="Joined"))
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=session_id, user_id=viewer_id))
    harness.run(_seed_message(
        harness.db, session_id=session_id, user_id=owner_id, tenant_id=TENANT,
        seq=1, content="owner first", role="user",
    ))
    harness.run(_seed_message(
        harness.db, session_id=session_id, user_id=owner_id, tenant_id=TENANT,
        seq=2, content="compressed summary", role="system", message_type="context_summary",
    ))

    default_view = _get(harness, monkeypatch, session_id=session_id, user_id=viewer_id)
    assert [m["content"] for m in default_view.data["messages"]] == ["owner first"]

    raw_view = _get(
        harness, monkeypatch, session_id=session_id, user_id=viewer_id, include_context_summary=True,
    )
    assert [m["content"] for m in raw_view.data["messages"]] == ["owner first", "compressed summary"]


# --- visibility matrix (404, never 403) ---


def test_non_member_get_returns_404(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id, title="Mine"))
    stranger_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Stranger"))

    with pytest.raises(HTTPException) as exc_info:
        _get(harness, monkeypatch, session_id=session_id, user_id=stranger_id)

    assert exc_info.value.status_code == 404


def test_removed_participant_get_returns_404_and_retrieves_no_messages(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    viewer_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Participant"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id, title="Joined"))
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=session_id, user_id=viewer_id))
    harness.run(_seed_message(
        harness.db, session_id=session_id, user_id=owner_id, tenant_id=TENANT,
        seq=1, content="owner first", role="user",
    ))
    harness.run(SessionParticipantsRepository(harness.db).remove(
        session_id, tenant_id=TENANT, user_id=viewer_id))

    with pytest.raises(HTTPException) as exc_info:
        _get(harness, monkeypatch, session_id=session_id, user_id=viewer_id)

    assert exc_info.value.status_code == 404


def test_cross_tenant_get_returns_404(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id="tenant-b", name="Owner"))
    session_id = harness.run(_seed_session(harness.db, tenant_id="tenant-b", owner_id=owner_id, title="Theirs"))
    outsider_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Outsider"))

    with pytest.raises(HTTPException) as exc_info:
        _get(harness, monkeypatch, session_id=session_id, user_id=outsider_id, tenant_id=TENANT)

    assert exc_info.value.status_code == 404


# --- clean parsing and preserved owner-only behaviour ---


def test_invalid_session_id_returns_400(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))

    with pytest.raises(HTTPException) as exc_info:
        _get(harness, monkeypatch, session_id="not-an-objectid", user_id=owner_id)

    assert exc_info.value.status_code == 400


def test_owner_get_clears_scheduled_unread_but_a_participant_get_does_not(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    viewer_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Participant"))
    session_id = harness.run(_seed_session(
        harness.db, tenant_id=TENANT, owner_id=owner_id, title="Joined", scheduled_unread=True))
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=session_id, user_id=viewer_id))

    # The participant's GET succeeds without clearing the owner's unread
    # signal (scheduled_unread is the owner's; todo 19 owns a participant
    # cursor). The clear's user_id filter scopes it to the owner.
    participant_view = _get(harness, monkeypatch, session_id=session_id, user_id=viewer_id)
    assert participant_view.data["scheduled_unread"] is True
    row = harness.run(harness.db.chat_sessions.find_one({"_id": ObjectId(session_id)}))
    assert row.get("scheduled_unread") is True

    owner_view = _get(harness, monkeypatch, session_id=session_id, user_id=owner_id)
    assert owner_view.data["scheduled_unread"] is True  # serialized before the clear
    row = harness.run(harness.db.chat_sessions.find_one({"_id": ObjectId(session_id)}))
    assert row.get("scheduled_unread") is False  # cleared by the owner's GET


# --- todo 5: seq / legacy_key / author / live_cursor projection ---------------


def test_messages_project_identity_seq_legacy_key_and_live_cursor(api_db, monkeypatch) -> None:
    monkeypatch.setattr(identity_projection, "ObjectStorageClient", _FakeStorage)
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    author_direct = harness.run(_seed_user_profile(
        harness.db, tenant_id=TENANT, name="Bob Member",
        avatar="https://cdn.example.com/bob.png",
    ))
    author_path = harness.run(_seed_user_profile(
        harness.db, tenant_id=TENANT, name="Carol Path",
        avatar_object_path="tenants/a/carol.png",
    ))
    session_id = harness.run(_seed_session(
        harness.db, tenant_id=TENANT, owner_id=owner_id, title="Joined", next_message_seq=4,
    ))
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=session_id, user_id=author_direct))
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=session_id, user_id=author_path))
    harness.run(_seed_message(
        harness.db, session_id=session_id, user_id=author_direct, tenant_id=TENANT,
        seq=1, content="hello", role="user", message_id="m-1",
    ))
    harness.run(_seed_message(
        harness.db, session_id=session_id, user_id=author_path, tenant_id=TENANT,
        seq=2, content="legacy one", role="user",
    ))
    harness.run(_seed_message(
        harness.db, session_id=session_id, user_id=author_path, tenant_id=TENANT,
        seq=3, content="legacy two", role="user",
    ))
    harness.run(_seed_message(
        harness.db, session_id=session_id, user_id=owner_id, tenant_id=TENANT,
        seq=4, content="answer", role="assistant",
    ))

    response = _get(harness, monkeypatch, session_id=session_id, user_id=owner_id)

    messages = response.data["messages"]
    assert [m["content"] for m in messages] == ["hello", "legacy one", "legacy two", "answer"]
    assert [m["seq"] for m in messages] == [1, 2, 3, 4]
    assert all(type(m["seq"]) is int and m["seq"] >= 0 for m in messages)
    assert [m["legacy_key"] for m in messages] == [
        "message:m-1", "legacy:user:2", "legacy:user:3", "legacy:assistant:4",
    ]
    assert all(isinstance(m["legacy_key"], str) and m["legacy_key"] for m in messages)
    # Two same-role rows with no message_id must NOT collapse under a
    # role-only key: each keeps its own allocated-ordinal key.
    assert len({messages[1]["legacy_key"], messages[2]["legacy_key"]}) == 2
    assert messages[0]["user_id"] == author_direct
    assert messages[0]["author"] == {
        "user_id": author_direct, "display_name": "Bob Member",
        "avatar_url": "https://cdn.example.com/bob.png",
    }
    signed_author = {
        "user_id": author_path, "display_name": "Carol Path",
        "avatar_url": "https://signed.example.com/carol.png?sig=test",
    }
    assert messages[1]["author"] == signed_author
    assert messages[2]["author"] == signed_author
    # Assistant rows carry no user author/avatar projection at all.
    assert messages[3]["author"] is None
    payload = json.dumps(response.data, default=str)
    assert "avatar_object_path" not in payload
    assert "tenants/a/carol.png" not in payload
    # The live cursor round-trips through T1's canonical validator.
    fields = parse_live_cursor(response.data["live_cursor"], session_id=session_id)
    assert fields["v"] == 1
    assert fields["last_message_seq"] == 4
    assert fields["active_message_id"] is None
    assert fields["active_stream_seq"] is None
    assert len(fields["revision"]) == 64


def test_backfill_persists_seq_and_survives_an_intervening_append(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id))
    row_id = harness.run(_seed_unsequenced_message(
        harness.db, session_id=session_id, user_id=owner_id, tenant_id=TENANT,
        content="historical row",
    ))

    first = _get(harness, monkeypatch, session_id=session_id, user_id=owner_id)
    assert [(m["seq"], m["legacy_key"]) for m in first.data["messages"]] == [
        (1, "legacy:user:1"),
    ]
    stored = harness.run(harness.db.chat_messages.find_one({"_id": ObjectId(row_id)}))
    assert stored["seq"] == 1  # persisted durably, never numbered at read time

    again = _get(harness, monkeypatch, session_id=session_id, user_id=owner_id)
    assert [(m["seq"], m["legacy_key"]) for m in again.data["messages"]] == [
        (1, "legacy:user:1"),
    ]

    repository = ConversationRepository(harness.db)
    appended = harness.run(repository.append_message(
        conversation_id=session_id, tenant_id=TENANT, user_id=owner_id,
        role="user", content="new turn", message_id="m-new",
    ))
    assert appended["seq"] == 2

    third = _get(harness, monkeypatch, session_id=session_id, user_id=owner_id)
    assert [(m["content"], m["seq"], m["legacy_key"]) for m in third.data["messages"]] == [
        ("historical row", 1, "legacy:user:1"),
        ("new turn", 2, "message:m-new"),
    ]


# Assertion fixture recorded for T8's client merge (not T8 behavior): the
# server-pinned order of a MIXED session served through the degrade path —
# the single unsequenced row FIRST (BSON orders a missing field before any
# number), then the already-sequenced rows by seq asc.
MIXED_DEGRADE_EXPECTED_ORDER = [
    ("legacy first", 0, "legacy:user:0"),
    ("newest", 7, "message:m-new"),
]


def test_mixed_session_degrades_without_backfill_and_pins_server_order(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    session_id = harness.run(_seed_session(
        harness.db, tenant_id=TENANT, owner_id=owner_id, next_message_seq=7,
    ))
    # Fixture insert order PINNED: the one unsequenced legacy row FIRST by
    # (created_at asc, _id asc); the already-sequenced newest row LAST.
    harness.run(_seed_unsequenced_message(
        harness.db, session_id=session_id, user_id=owner_id, tenant_id=TENANT,
        content="legacy first", created_at=_at(-100),
    ))
    harness.run(_seed_message(
        harness.db, session_id=session_id, user_id=owner_id, tenant_id=TENANT,
        seq=7, content="newest", message_id="m-new", created_at=_at(0),
    ))
    # One unsequenced row is the index maximum: a second one raises E11000,
    # which is exactly why the mixed shape cannot be wider than this.
    with pytest.raises(DuplicateKeyError):
        harness.run(_seed_unsequenced_message(
            harness.db, session_id=session_id, user_id=owner_id, tenant_id=TENANT,
            content="second legacy", created_at=_at(-50),
        ))

    response = _get(harness, monkeypatch, session_id=session_id, user_id=owner_id)

    assert [
        (m["content"], m["seq"], m["legacy_key"]) for m in response.data["messages"]
    ] == MIXED_DEGRADE_EXPECTED_ORDER
    # 0 is reserved for the degraded row; allocation starts at 1.
    assert response.data["messages"][0]["seq"] == 0
    assert response.data["messages"][0]["legacy_key"] == "legacy:user:0"
    # The backfill gate left the session untouched.
    legacy_row = harness.run(harness.db.chat_messages.find_one({"content": "legacy first"}))
    assert legacy_row.get("seq") is None
    session_row = harness.run(harness.db.chat_sessions.find_one({"_id": ObjectId(session_id)}))
    assert session_row["next_message_seq"] == 7
    fields = parse_live_cursor(response.data["live_cursor"], session_id=session_id)
    assert fields["last_message_seq"] == 7


def test_concurrent_backfill_assigns_one_ordinal_without_duplicates(api_db) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id))
    row_id = harness.run(_seed_unsequenced_message(
        harness.db, session_id=session_id, user_id=owner_id, tenant_id=TENANT,
        content="only legacy row",
    ))
    repository = ConversationRepository(harness.db)

    async def _race() -> list[int]:
        return list(await asyncio.gather(
            repository.backfill_message_sequences(TENANT, session_id),
            repository.backfill_message_sequences(TENANT, session_id),
        ))

    results = harness.run(_race())
    assert sum(results) == 1  # exactly one writer won the single ordinal
    stored = harness.run(harness.db.chat_messages.find_one({"_id": ObjectId(row_id)}))
    assert type(stored["seq"]) is int and stored["seq"] >= 1
    assert harness.run(harness.db.chat_messages.count_documents(
        {"session_id": ObjectId(session_id), "seq": stored["seq"]},
    )) == 1


def test_message_author_null_for_missing_user_and_missing_avatar(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    ghost_id = str(ObjectId())
    named_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="No Avatar"))
    session_id = harness.run(_seed_session(
        harness.db, tenant_id=TENANT, owner_id=owner_id, next_message_seq=3,
    ))
    harness.run(_seed_message(
        harness.db, session_id=session_id, user_id=ghost_id, tenant_id=TENANT,
        seq=1, content="ghost author",
    ))
    harness.run(_seed_message(
        harness.db, session_id=session_id, user_id=named_id, tenant_id=TENANT,
        seq=2, content="named author",
    ))
    harness.run(_seed_message(
        harness.db, session_id=session_id, user_id=owner_id, tenant_id=TENANT,
        seq=3, content="assistant", role="assistant",
    ))

    response = _get(harness, monkeypatch, session_id=session_id, user_id=owner_id)

    messages = response.data["messages"]
    assert messages[0]["user_id"] == ghost_id
    assert messages[0]["author"] is None
    assert messages[1]["author"] == {
        "user_id": named_id, "display_name": "No Avatar", "avatar_url": None,
    }
    assert messages[2]["author"] is None


def test_message_author_cross_tenant_user_is_not_projected(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    foreign_id = harness.run(_seed_user(harness.db, tenant_id="tenant-b", name="Tenant B Secret"))
    session_id = harness.run(_seed_session(
        harness.db, tenant_id=TENANT, owner_id=owner_id, next_message_seq=1,
    ))
    harness.run(_seed_message(
        harness.db, session_id=session_id, user_id=foreign_id, tenant_id=TENANT,
        seq=1, content="foreign authored",
    ))

    response = _get(harness, monkeypatch, session_id=session_id, user_id=owner_id)

    assert response.data["messages"][0]["user_id"] == foreign_id
    assert response.data["messages"][0]["author"] is None
    assert "Tenant B Secret" not in json.dumps(response.data, default=str)


def test_removed_historical_author_still_resolves(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    author_id = harness.run(_seed_user_profile(
        harness.db, tenant_id=TENANT, name="Former Member",
        avatar="https://cdn.example.com/former.png",
    ))
    session_id = harness.run(_seed_session(
        harness.db, tenant_id=TENANT, owner_id=owner_id, next_message_seq=1,
    ))
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=session_id, user_id=author_id))
    harness.run(_seed_message(
        harness.db, session_id=session_id, user_id=author_id, tenant_id=TENANT,
        seq=1, content="historical reply",
    ))
    harness.run(SessionParticipantsRepository(harness.db).remove(
        session_id, tenant_id=TENANT, user_id=author_id))

    response = _get(harness, monkeypatch, session_id=session_id, user_id=owner_id)

    assert response.data["messages"][0]["author"] == {
        "user_id": author_id, "display_name": "Former Member",
        "avatar_url": "https://cdn.example.com/former.png",
    }


def test_backfill_forward_fix_round_trip_restores_row_to_pool(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id))
    row_id = harness.run(_seed_unsequenced_message(
        harness.db, session_id=session_id, user_id=owner_id, tenant_id=TENANT,
        content="historical body",
    ))

    first = _get(harness, monkeypatch, session_id=session_id, user_id=owner_id)
    assert first.data["messages"][0]["seq"] == 1

    # Forward fix: clearing the backfilled seq returns the row to the pool.
    harness.run(harness.db.chat_messages.update_one(
        {"_id": ObjectId(row_id)}, {"$unset": {"seq": ""}},
    ))
    cleared = harness.run(harness.db.chat_messages.find_one({"_id": ObjectId(row_id)}))
    assert cleared.get("seq") is None
    assert cleared["content"] == "historical body"
    counter_before = harness.run(harness.db.chat_sessions.find_one({"_id": ObjectId(session_id)}))
    assert counter_before["next_message_seq"] == 1  # clearing never rewinds the counter

    second = _get(harness, monkeypatch, session_id=session_id, user_id=owner_id)

    stored = harness.run(harness.db.chat_messages.find_one({"_id": ObjectId(row_id)}))
    assert stored["content"] == "historical body"  # content is never rewritten
    assert type(stored["seq"]) is int and stored["seq"] >= 2
    assert second.data["messages"][0]["seq"] == stored["seq"]
    counter_after = harness.run(harness.db.chat_sessions.find_one({"_id": ObjectId(session_id)}))
    assert counter_after["next_message_seq"] == stored["seq"]  # counter moved forward only


def test_live_cursor_tracks_durable_active_stream_high_water(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    session_id = harness.run(_seed_session(
        harness.db, tenant_id=TENANT, owner_id=owner_id, next_message_seq=3,
        active_run={
            "run_id": "r-1", "message_id": "m-live", "initiator_user_id": owner_id,
            "status": "running", "started_at": _now(),
        },
    ))
    harness.run(_seed_message(
        harness.db, session_id=session_id, user_id=owner_id, tenant_id=TENANT,
        seq=3, content="streaming", role="assistant", message_id="m-live",
    ))
    harness.run(harness.db.kernel_event_projections.insert_many([
        {"event_id": "e-2", "tenant_id": TENANT, "message_id": "m-live", "stream_seq": 2},
        {"event_id": "e-5", "tenant_id": TENANT, "message_id": "m-live", "stream_seq": 5},
    ]))

    response = _get(harness, monkeypatch, session_id=session_id, user_id=owner_id)

    fields = parse_live_cursor(response.data["live_cursor"], session_id=session_id)
    assert fields["last_message_seq"] == 3
    assert fields["active_message_id"] == "m-live"
    assert fields["active_stream_seq"] == 5

    # A terminal run closes the active pair in the authoritative cursor.
    harness.run(harness.db.chat_sessions.update_one(
        {"_id": ObjectId(session_id)}, {"$set": {"active_run.status": "completed"}},
    ))
    terminal = _get(harness, monkeypatch, session_id=session_id, user_id=owner_id)
    terminal_fields = parse_live_cursor(terminal.data["live_cursor"], session_id=session_id)
    assert terminal_fields["active_message_id"] is None
    assert terminal_fields["active_stream_seq"] is None
