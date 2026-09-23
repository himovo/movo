"""Endpoint-level tests for the participant read cursor and the shared unread
signal (plan todo 19).

Pinned contract:

- An active participant's ``GET /sessions/{session_id}`` advances their
  ``last_read_seq`` to the session's max seq (T2's ``set_read_cursor``).
- ``scope=shared`` list rows expose ``shared_unread: bool`` computed from the
  viewer's ``last_read_seq`` vs the session's max seq. DSH sessions carry
  ``next_message_seq`` and every DSH append mints the message's seq AS the new
  counter value (``app/dsh_runtime/conversation/repository.py``), so
  ``next_message_seq`` equals the session's max message seq; legacy sessions
  without the field fall back to the messages' max seq (pinned decision). A
  session with no messages is never unread.
- Owner rows keep ``scheduled_unread`` and are unaffected: the owner's list
  never gains ``shared_unread``, a participant's GET does not clear the
  owner's flag, and the clear stays owner-scoped (the owner's own GET clears).
- A participant whose cursor is unset or reset to 0 (T2's re-join reset) is
  unread when the session has messages; a removed participant accrues no
  unread state (their row is inactive).

TDD phases: baseline characterization (the ``*_today`` pins and the three
owner-safety pins pass on the UNCHANGED code) -> RED (the cursor/unread tests
below fail on the unchanged code: no ``shared_unread`` field, no cursor
advance) -> GREEN (the two superseded ``*_today`` pins REMOVED — the planned
behavior change, recorded in T19-failure.txt).
"""

# allow: SIZE_OK — cohesive pinned matrix over the participant-read-cursor
# seam; T04/T07/T08/T09 precedent for session-sharing endpoint test files.

from __future__ import annotations

import datetime
from typing import Any

import pytest
from bson import ObjectId

from app.api.endpoints import sessions
from app.dsh_runtime.conversation.participants_repository import SessionParticipantsRepository
from app.dsh_runtime.conversation.repository import ConversationRepository


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
    # Legacy-shaped session doc: NO next_message_seq field (only
    # ConversationRepository.create seeds it). Used verbatim where a legacy
    # session is wanted; DSH-parity sessions are seeded via repo.create().
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
    # The session-scoped message read and the legacy max-seq fallback are
    # served by the unique per-session sequence index (created by
    # ConversationRepository.ensure_indexes() in production) — the fixture
    # mirrors the production requirement without executing that module.
    harness.run(harness.db.chat_messages.create_index(
        [("main_id", 1), ("session_id", 1), ("seq", 1)],
        unique=True,
        name="unique_main_session_seq",
    ))
    # The owner path's .hint() requires this index (created by the startup
    # block, app/main.py:225) — a hinted query against an index-less
    # collection raises OperationFailure, so the fixture mirrors production
    # (T8's fixture precedent).
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
    # module-level seam (T8's pattern) so each test drives the handler directly
    # as a specific seeded viewer. Every Query-defaulted parameter is passed
    # explicitly — a handler called outside FastAPI keeps the raw Query(...)
    # default objects, which are truthy. ``scope`` is passed only when
    # explicitly given so the characterization tests exercise the scope-less
    # request path (as the frontend does).
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


def _get(
    harness: Any,
    monkeypatch: Any,
    *,
    session_id: str,
    user_id: str,
    tenant_id: str = TENANT,
    include_context_summary: bool = False,
) -> Any:
    # T9's helper: the endpoint resolves the viewer from the authorization
    # header; patch the module-level seam so each test drives the handler
    # directly as a specific seeded viewer, passing every Query-defaulted
    # parameter explicitly.
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


async def _participant_row(db: Any, *, session_id: str, user_id: str, tenant_id: str = TENANT) -> Any:
    return await db.session_participants.find_one(
        {"main_id": tenant_id, "conversation_id": session_id, "user_id": user_id}
    )


def _dsh_session(harness: Any, *, owner_id: str, title: str = "Shared") -> tuple[Any, str]:
    repo = ConversationRepository(harness.db)
    doc = harness.run(repo.create(tenant_id=TENANT, user_id=owner_id, title=title))
    return repo, str(doc["_id"])


# --- owner-safety characterization (passes on the UNCHANGED code and after) ---
#
# The two superseded baseline pins (scope=shared rows had no unread signal; a
# participant's GET advanced no cursor) were REMOVED at GREEN: todo 19's
# planned behavior change replaces both. Recorded in T19-failure.txt.


def test_owner_list_items_never_gain_shared_unread(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    viewer_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Participant"))
    repo, session_id = _dsh_session(harness, owner_id=owner_id, title="Joined")
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=session_id, user_id=viewer_id))
    harness.run(repo.append_message(
        conversation_id=session_id, tenant_id=TENANT, user_id=owner_id,
        role="user", content="hello from the owner", message_id="owner-msg-1",
    ))

    response = _list(harness, monkeypatch, user_id=owner_id)

    # The owner's own list items are SessionSummary models without the
    # participant signal — the owner never gains shared_unread.
    items = response.data
    assert [item.id for item in items] == [session_id]
    assert all("shared_unread" not in item.model_dump() for item in items)


def test_owner_scheduled_unread_lifecycle_stays_owner_scoped(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    viewer_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Participant"))
    session_id = harness.run(_seed_session(
        harness.db, tenant_id=TENANT, owner_id=owner_id, title="Joined", scheduled_unread=True))
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=session_id, user_id=viewer_id))

    # The participant's GET never clears the owner's flag; only the owner's
    # own GET does (T9's pinned owner-scoped clear).
    participant_view = _get(harness, monkeypatch, session_id=session_id, user_id=viewer_id)
    assert participant_view.data["scheduled_unread"] is True
    row = harness.run(harness.db.chat_sessions.find_one({"_id": ObjectId(session_id)}))
    assert row.get("scheduled_unread") is True

    owner_view = _get(harness, monkeypatch, session_id=session_id, user_id=owner_id)
    assert owner_view.data["scheduled_unread"] is True  # serialized before the clear
    row = harness.run(harness.db.chat_sessions.find_one({"_id": ObjectId(session_id)}))
    assert row.get("scheduled_unread") is False  # cleared by the owner's GET


def test_removed_participant_accrues_no_unread_state(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    viewer_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Participant"))
    repo, session_id = _dsh_session(harness, owner_id=owner_id, title="Joined")
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=session_id, user_id=viewer_id))
    harness.run(repo.append_message(
        conversation_id=session_id, tenant_id=TENANT, user_id=owner_id,
        role="user", content="hello from the owner", message_id="owner-msg-1",
    ))
    harness.run(SessionParticipantsRepository(harness.db).remove(
        session_id, tenant_id=TENANT, user_id=viewer_id))

    # The removed participant's row is inactive: the shared list excludes the
    # session for them entirely, so no unread state accrues.
    response = _list(harness, monkeypatch, user_id=viewer_id, scope="shared")
    assert response.data == []
    row = harness.run(_participant_row(harness.db, session_id=session_id, user_id=viewer_id))
    assert row.get("removed_at") is not None


# --- the participant read cursor and shared_unread (RED until implemented) ---


def test_participants_shared_row_is_unread_after_the_owner_sends(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    viewer_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Participant"))
    repo, session_id = _dsh_session(harness, owner_id=owner_id, title="Joined")
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=session_id, user_id=viewer_id))
    harness.run(repo.append_message(
        conversation_id=session_id, tenant_id=TENANT, user_id=owner_id,
        role="user", content="hello from the owner", message_id="owner-msg-1",
    ))

    response = _list(harness, monkeypatch, user_id=viewer_id, scope="shared")

    # The participant's cursor is 0 (T2's join reset) and the session has
    # messages: unread.
    items = response.data
    assert [item["id"] for item in items] == [session_id]
    assert items[0]["shared_unread"] is True


def test_participants_shared_row_is_read_after_they_get_the_session(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    viewer_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Participant"))
    repo, session_id = _dsh_session(harness, owner_id=owner_id, title="Joined")
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=session_id, user_id=viewer_id))
    harness.run(repo.append_message(
        conversation_id=session_id, tenant_id=TENANT, user_id=owner_id,
        role="user", content="hello from the owner", message_id="owner-msg-1",
    ))

    _get(harness, monkeypatch, session_id=session_id, user_id=viewer_id)

    # The participant's GET advanced their cursor to the session's max seq:
    # the shared row reads as clear.
    response = _list(harness, monkeypatch, user_id=viewer_id, scope="shared")
    items = response.data
    assert [item["id"] for item in items] == [session_id]
    assert items[0]["shared_unread"] is False


def test_participant_get_advances_last_read_seq_to_the_sessions_max_seq(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    viewer_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Participant"))
    repo, session_id = _dsh_session(harness, owner_id=owner_id, title="Joined")
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=session_id, user_id=viewer_id))
    harness.run(repo.append_message(
        conversation_id=session_id, tenant_id=TENANT, user_id=owner_id,
        role="user", content="hello from the owner", message_id="owner-msg-1",
    ))

    _get(harness, monkeypatch, session_id=session_id, user_id=viewer_id)

    # The cursor equals the session's max seq — for a DSH session that is
    # exactly next_message_seq (every append mints seq AS the new counter).
    row = harness.run(_participant_row(harness.db, session_id=session_id, user_id=viewer_id))
    session_doc = harness.run(harness.db.chat_sessions.find_one({"_id": ObjectId(session_id)}))
    assert int(row.get("last_read_seq") or 0) == int(session_doc.get("next_message_seq") or 0) == 1


def test_rejoin_reset_cursor_makes_the_session_unread_again(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    viewer_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Participant"))
    repo, session_id = _dsh_session(harness, owner_id=owner_id, title="Joined")
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=session_id, user_id=viewer_id))
    harness.run(repo.append_message(
        conversation_id=session_id, tenant_id=TENANT, user_id=owner_id,
        role="user", content="hello from the owner", message_id="owner-msg-1",
    ))

    _get(harness, monkeypatch, session_id=session_id, user_id=viewer_id)
    harness.run(SessionParticipantsRepository(harness.db).remove(
        session_id, tenant_id=TENANT, user_id=viewer_id))
    # Re-join: T2's add() resets last_read_seq to 0 on the reused row.
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=session_id, user_id=viewer_id))

    row = harness.run(_participant_row(harness.db, session_id=session_id, user_id=viewer_id))
    assert int(row.get("last_read_seq") or 0) == 0

    response = _list(harness, monkeypatch, user_id=viewer_id, scope="shared")
    assert [item["id"] for item in response.data] == [session_id]
    assert response.data[0]["shared_unread"] is True


def test_legacy_session_without_next_message_seq_uses_the_messages_max_seq(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    viewer_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Participant"))
    session_id = harness.run(_seed_session(harness.db, tenant_id=TENANT, owner_id=owner_id, title="Legacy"))
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=session_id, user_id=viewer_id))
    harness.run(_seed_message(
        harness.db, session_id=session_id, user_id=owner_id, tenant_id=TENANT,
        seq=1, content="legacy first", role="user",
    ))
    harness.run(_seed_message(
        harness.db, session_id=session_id, user_id=owner_id, tenant_id=TENANT,
        seq=2, content="legacy second", role="assistant",
    ))

    # Pinned decision: a legacy session without next_message_seq falls back to
    # the messages' max seq — an unset cursor is unread when messages exist.
    response = _list(harness, monkeypatch, user_id=viewer_id, scope="shared")
    assert [item["id"] for item in response.data] == [session_id]
    assert response.data[0]["shared_unread"] is True

    _get(harness, monkeypatch, session_id=session_id, user_id=viewer_id)

    row = harness.run(_participant_row(harness.db, session_id=session_id, user_id=viewer_id))
    assert int(row.get("last_read_seq") or 0) == 2  # the messages' max seq

    response = _list(harness, monkeypatch, user_id=viewer_id, scope="shared")
    assert response.data[0]["shared_unread"] is False


def test_session_with_no_messages_is_not_unread(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    viewer_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Participant"))
    _repo, session_id = _dsh_session(harness, owner_id=owner_id, title="Quiet")

    harness.run(_join(harness.db, tenant_id=TENANT, session_id=session_id, user_id=viewer_id))

    # No messages: nothing to read, never unread.
    response = _list(harness, monkeypatch, user_id=viewer_id, scope="shared")
    assert [item["id"] for item in response.data] == [session_id]
    assert response.data[0]["shared_unread"] is False


def test_paged_shared_rows_carry_shared_unread(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    viewer_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Participant"))
    repo, session_id = _dsh_session(harness, owner_id=owner_id, title="Joined")
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=session_id, user_id=viewer_id))
    harness.run(repo.append_message(
        conversation_id=session_id, tenant_id=TENANT, user_id=owner_id,
        role="user", content="hello from the owner", message_id="owner-msg-1",
    ))

    response = _list(harness, monkeypatch, user_id=viewer_id, scope="shared", paged=True, limit=30, offset=0)

    # Both shared-list call shapes (paged + non-paged) expose the signal.
    items = response.data["items"]
    assert [item["id"] for item in items] == [session_id]
    assert items[0]["shared_unread"] is True


def test_shared_unread_is_per_participant(api_db, monkeypatch) -> None:
    harness = api_db
    owner_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Owner"))
    first_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="First"))
    second_id = harness.run(_seed_user(harness.db, tenant_id=TENANT, name="Second"))
    repo, session_id = _dsh_session(harness, owner_id=owner_id, title="Joined")
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=session_id, user_id=first_id))
    harness.run(_join(harness.db, tenant_id=TENANT, session_id=session_id, user_id=second_id))
    harness.run(repo.append_message(
        conversation_id=session_id, tenant_id=TENANT, user_id=owner_id,
        role="user", content="hello from the owner", message_id="owner-msg-1",
    ))

    _get(harness, monkeypatch, session_id=session_id, user_id=first_id)

    # Each participant's shared list reflects THEIR OWN cursor.
    first_view = _list(harness, monkeypatch, user_id=first_id, scope="shared")
    assert [item["id"] for item in first_view.data] == [session_id]
    assert first_view.data[0]["shared_unread"] is False

    second_view = _list(harness, monkeypatch, user_id=second_id, scope="shared")
    assert [item["id"] for item in second_view.data] == [session_id]
    assert second_view.data[0]["shared_unread"] is True
