"""Endpoint-level tests for the ``GET /sessions`` scope parameter (plan todo 8).

Pinned contract:

- The owner scope keeps today's behaviour exactly: same hinted query (the
  ``.hint([user_id, updated_at desc, _id desc])`` cursor), same response — a
  characterization test captures the executed query and fails if the hint is
  dropped or an ``$or`` union is introduced (either would blow up the pinned
  index).
- ``scope=shared`` returns the sessions the viewer actively participates in
  (``session_participants`` rows with ``removed_at`` null), with its own
  ``limit``/``offset``/``has_more``, ordered by the sessions' own activity
  (``updated_at`` desc) — never by the participants index's ``joined_at``.
- Unknown scope values fall back to the owner scope (pinned decision; the
  endpoint's existing lenient Query style carries no strict validation).
"""

# allow: SIZE_OK — cohesive 10-test pinned matrix over one API surface
# (characterization + scope=shared); T04 precedent for session-sharing
# endpoint test files.

from __future__ import annotations

import datetime
from typing import Any

import pytest
from bson import ObjectId

from app.api.endpoints import sessions
from app.dsh_runtime.conversation.participants_repository import SessionParticipantsRepository


TENANT = "tenant-a"
OWNER_HINT = [("user_id", 1), ("updated_at", -1), ("_id", -1)]


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
) -> str:
    now = updated_at or _now()
    result = await db.chat_sessions.insert_one({
        "user_id": owner_id,
        "main_id": tenant_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
    })
    return str(result.inserted_id)


async def _join(db: Any, *, tenant_id: str, session_id: str, user_id: str) -> None:
    await SessionParticipantsRepository(db).add(
        tenant_id=tenant_id, conversation_id=session_id, user_id=user_id
    )


@pytest.fixture
def api_db(real_mongo_db, monkeypatch):
    harness = real_mongo_db
    monkeypatch.setattr(sessions, "get_db", lambda: harness.db)
    harness.run(SessionParticipantsRepository(harness.db).ensure_indexes())
    # The owner path's .hint() requires this index (created by the startup block,
    # app/main.py:225) — a hinted query against an index-less collection raises
    # OperationFailure, so the fixture mirrors the production requirement.
    harness.run(harness.db.chat_sessions.create_index(
        [("user_id", 1), ("updated_at", -1), ("_id", -1)]
    ))
    return harness


def _list(
    harness: Any,
    monkeypatch: Any,
    *,
    user_id: str,
    tenant_id: str = TENANT,
    paged: bool = False,
    limit: int = 30,
    offset: int = 0,
    scope: str | None = None,
) -> Any:
    # The endpoint resolves the viewer from the authorization header; patch the
    # module-level seam (mirrors T4's principal bypass) so each test drives the
    # handler directly as a specific seeded viewer. Every Query-defaulted
    # parameter is passed explicitly — a handler called outside FastAPI keeps
    # the raw Query(...) default objects, which are truthy. ``scope`` is passed
    # only when explicitly given so the characterization tests exercise the
    # scope-less request path (as the frontend does).
    async def _fake_resolve(authorization: str | None) -> dict[str, Any]:
        return {"user": {"_id": ObjectId(user_id)}, "main_id": tenant_id}

    monkeypatch.setattr(sessions, "_resolve_session_user", _fake_resolve)
    request: dict[str, Any] = {
        "user_id": user_id,
        "main_id": tenant_id,
        "main_id_snake": None,
        "paged": paged,
        "limit": limit,
        "offset": offset,
        "authorization": None,
    }
    if scope is not None:
        request["scope"] = scope
    return harness.run(sessions.list_sessions(**request))


# --- baseline characterization: owner scope unchanged (passes on the UNCHANGED code) ---


class _DbProxy:
    def __init__(self, db: Any, collection_name: str, collection: Any) -> None:
        self._db = db
        self._collection_name = collection_name
        self._collection = collection

    def __getattr__(self, name: str) -> Any:
        if name == self._collection_name:
            return self._collection
        return getattr(self._db, name)


def test_owner_scope_characterization_query_and_response_pinned(api_db, monkeypatch) -> None:
    harness = api_db
    viewer_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Viewer"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=viewer_id, title="Mine"))

    captured: dict[str, Any] = {}

    class _CursorProxy:
        def __init__(self, cursor: Any) -> None:
            self._cursor = cursor

        def sort(self, *args: Any, **kwargs: Any) -> "_CursorProxy":
            captured["sort"] = args
            return _CursorProxy(self._cursor.sort(*args, **kwargs))

        def hint(self, *args: Any, **kwargs: Any) -> "_CursorProxy":
            captured["hint"] = args
            return _CursorProxy(self._cursor.hint(*args, **kwargs))

        def skip(self, *args: Any, **kwargs: Any) -> "_CursorProxy":
            captured["skip"] = args
            return _CursorProxy(self._cursor.skip(*args, **kwargs))

        def limit(self, *args: Any, **kwargs: Any) -> "_CursorProxy":
            captured["limit"] = args
            return _CursorProxy(self._cursor.limit(*args, **kwargs))

        def __aiter__(self) -> Any:
            return self._cursor.__aiter__()

    class _CollectionProxy:
        def __init__(self, collection: Any) -> None:
            self._collection = collection

        def find(self, filter: Any, *args: Any, **kwargs: Any) -> Any:
            captured["filter"] = filter
            return _CursorProxy(self._collection.find(filter, *args, **kwargs))

    proxy_db = _DbProxy(harness.db, "chat_sessions", _CollectionProxy(harness.db.chat_sessions))
    monkeypatch.setattr(sessions, "get_db", lambda: proxy_db)

    response = _list(harness, monkeypatch, user_id=viewer_id, paged=True, limit=30, offset=0)

    # Query shape: owner filter, activity sort, the pinned hint — no $or union.
    assert captured["filter"]["user_id"] == viewer_id
    assert "$or" not in captured["filter"]
    assert captured["hint"] == (OWNER_HINT,)
    assert captured["sort"] == ([("updated_at", -1), ("_id", -1)],)
    assert captured["skip"] == (0,)
    assert captured["limit"] == (31,)

    # Response: today's serialized fields for the owned session.
    # The owner path builds SessionSummary models; the wire shape is the same.
    items = response.data["items"]
    assert [item.id for item in items] == [session_id]
    mine = items[0]
    mine_wire = mine.model_dump()
    assert mine.user_id == viewer_id
    assert mine.main_id == TENANT
    assert mine.title == "Mine"
    assert mine.message_count == 0
    assert mine.scheduled_unread is False
    assert mine.execution_location == "server"
    assert mine.pending_approval_count == 0
    assert response.data["has_more"] is False
    assert "access" not in mine_wire  # owner list payload unchanged by this todo
    assert "participant_count" not in mine_wire


def test_owner_scope_unpaged_characterization(api_db, monkeypatch) -> None:
    harness = api_db
    viewer_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Viewer"))
    first = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=viewer_id, updated_at=_at(-200)))
    second = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=viewer_id, updated_at=_at(-100)))

    response = _list(harness, monkeypatch, user_id=viewer_id)

    assert isinstance(response.data, list)
    assert [item.id for item in response.data] == [second, first]


def test_unknown_scope_value_falls_back_to_owner_scope(api_db, monkeypatch) -> None:
    harness = api_db
    viewer_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Viewer"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=viewer_id))
    other_owner = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Other"))
    harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=other_owner, title="Not mine"))

    response = _list(harness, monkeypatch, user_id=viewer_id, scope="bogus", paged=True)

    assert [item.id for item in response.data["items"]] == [session_id]


# --- scope=shared (RED until implemented) ---


def test_shared_scope_returns_joined_session_with_access_and_count(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    viewer_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Participant"))
    joined_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id, title="Joined"))
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=joined_id, user_id=viewer_id))
    other_owner = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Other"))
    harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=other_owner, title="Not mine"))

    response = _list(harness, monkeypatch, user_id=viewer_id, scope="shared", paged=True)

    items = response.data["items"]
    assert [item["id"] for item in items] == [joined_id]
    shared = items[0]
    assert shared["access"] == "shared"
    assert shared["owner_user_id"] == owner_id
    assert shared["user_id"] == owner_id  # session doc's user_id remains the owner
    assert shared["participant_count"] == 1  # the viewer's active non-owner row
    assert shared["main_id"] == TENANT
    assert shared["title"] == "Joined"
    assert response.data["has_more"] is False


def test_shared_scope_orders_by_session_activity_not_join_order(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    viewer_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Participant"))
    stale_id = harness.run(_seed_session(
        harness.db, tenant_id=TENANT, owner_id=owner_id, updated_at=_at(-500), title="Stale"))
    fresh_id = harness.run(_seed_session(
        harness.db, tenant_id=TENANT, owner_id=owner_id, updated_at=_at(-10), title="Fresh"))
    # Join the STALE session LAST so joined_at desc would put it first.
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=fresh_id, user_id=viewer_id))
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=stale_id, user_id=viewer_id))

    response = _list(harness, monkeypatch, user_id=viewer_id, scope="shared", paged=True)

    assert [item["id"] for item in response.data["items"]] == [fresh_id, stale_id]


def test_shared_scope_newer_message_sorts_above_earlier_join(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    viewer_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Participant"))
    quiet_id = harness.run(_seed_session(
        harness.db, tenant_id=TENANT, owner_id=owner_id, updated_at=_at(-500), title="Quiet"))
    active_id = harness.run(_seed_session(
        harness.db, tenant_id=TENANT, owner_id=owner_id, updated_at=_at(-400), title="Active"))
    # A newer message on the older-joined session bumps its activity above.
    bump = harness.db.chat_sessions.update_one(
        {"_id": ObjectId(quiet_id)},
        {"$set": {"updated_at": _at(-5), "last_message_at": _at(-5)}},
    )
    harness.run(bump)
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=active_id, user_id=viewer_id))
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=quiet_id, user_id=viewer_id))

    response = _list(harness, monkeypatch, user_id=viewer_id, scope="shared", paged=True)

    assert [item["id"] for item in response.data["items"]] == [quiet_id, active_id]


def test_shared_scope_empty_page_for_user_with_no_participations(api_db, monkeypatch) -> None:
    harness = api_db
    viewer_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Loner"))
    other_owner = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Other"))
    harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=other_owner, title="Not mine"))

    response = _list(harness, monkeypatch, user_id=viewer_id, scope="shared", paged=True)

    assert response.data["items"] == []
    assert response.data["has_more"] is False
    assert response.data["offset"] == 0


def test_shared_scope_excludes_left_and_removed_sessions(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    viewer_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Participant"))
    active_id = harness.run(_seed_session(
        harness.db, tenant_id=TENANT, owner_id=owner_id, updated_at=_at(-100), title="Active"))
    left_id = harness.run(_seed_session(
        harness.db, tenant_id=TENANT, owner_id=owner_id, updated_at=_at(-50), title="Left"))
    removed_id = harness.run(_seed_session(
        harness.db, tenant_id=TENANT, owner_id=owner_id, updated_at=_at(-10), title="Removed"))
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=active_id, user_id=viewer_id))
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=left_id, user_id=viewer_id))
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=removed_id, user_id=viewer_id))
    harness.run(SessionParticipantsRepository(harness.db).remove(
        left_id, tenant_id=TENANT, user_id=viewer_id))
    # Raw soft-remove on the third row (same removed_at: None escape-hatch state).
    harness.run(harness.db.session_participants.update_one(
        {"main_id": TENANT, "conversation_id": removed_id, "user_id": viewer_id},
        {"$set": {"removed_at": datetime.datetime.now(datetime.timezone.utc)}},
    ))

    response = _list(harness, monkeypatch, user_id=viewer_id, scope="shared", paged=True)

    assert [item["id"] for item in response.data["items"]] == [active_id]


def test_shared_scope_pagination_has_more(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    viewer_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Participant"))
    ids = []
    for idx in range(3):
        ids.append(harness.run(_seed_session(
            harness.db, tenant_id=TENANT, owner_id=owner_id,
            updated_at=_at(-100 + idx), title=f"S{idx}")))
        harness.run(_join(harness.db, tenant_id=TENANT, session_id=ids[-1], user_id=viewer_id))

    page_one = _list(harness, monkeypatch, user_id=viewer_id, scope="shared", paged=True, limit=2, offset=0)
    page_two = _list(harness, monkeypatch, user_id=viewer_id, scope="shared", paged=True, limit=2, offset=2)

    assert [item["id"] for item in page_one.data["items"]] == [ids[2], ids[1]]
    assert page_one.data["has_more"] is True
    assert page_one.data["limit"] == 2
    assert [item["id"] for item in page_two.data["items"]] == [ids[0]]
    assert page_two.data["has_more"] is False


def test_shared_scope_participant_count_counts_active_rows_per_session(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    viewer_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="P1"))
    third_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="P2"))
    shared_id = harness.run(_seed_session(
        harness.db, tenant_id=TENANT, owner_id=owner_id, updated_at=_at(-100), title="Busy"))
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=shared_id, user_id=viewer_id))
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=shared_id, user_id=third_id))
    left_id = harness.run(_seed_session(
        harness.db, tenant_id=TENANT, owner_id=owner_id, updated_at=_at(-90), title="Quiet"))
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=left_id, user_id=viewer_id))
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=left_id, user_id=third_id))
    harness.run(SessionParticipantsRepository(harness.db).remove(
        left_id, tenant_id=TENANT, user_id=third_id))

    response = _list(harness, monkeypatch, user_id=viewer_id, scope="shared", paged=True)

    counts = {item["id"]: item["participant_count"] for item in response.data["items"]}
    assert counts[shared_id] == 2  # viewer + third, both active
    assert counts[left_id] == 1  # the viewer's row; the removed third row does not count
