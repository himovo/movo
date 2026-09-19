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

import datetime
from typing import Any

import pytest
from bson import ObjectId
from fastapi import HTTPException

from app.api.endpoints import sessions
from app.dsh_runtime.conversation.participants_repository import SessionParticipantsRepository


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
) -> str:
    now = updated_at or _now()
    result = await db.chat_sessions.insert_one({
        "user_id": owner_id,
        "main_id": tenant_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "scheduled_unread": scheduled_unread,
    })
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
) -> None:
    await db.chat_messages.insert_one({
        "session_id": ObjectId(session_id),
        "user_id": user_id,
        "main_id": tenant_id,
        "role": role,
        "content": content,
        "created_at": _at(-100),
        "seq": seq,
        "message_type": message_type,
        "message_id": None,
    })


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
