"""Real-mongod coverage for session-scoped conversation repository reads and writes.

Todo 6: reads and writes are authorized/attributed by SESSION membership, not
by the viewer's user_id. `owned()` stays owner-only for owner-only operations;
`message()`/`update_assistant_projection` drop the viewer filter;
`append_message` and the run-state writes scope by `{_id, main_id}`; the
counter is seeded against legacy drift before the seq is minted.
"""

# allow: SIZE_OK — one cohesive seam (the conversation repository's session
# scoping), 20 real-mongod tests pinned to the frozen plan's todo-6 matrix;
# mirrors T04's pinned single-file test matrix.

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.dsh_runtime.conversation import ConversationRepository
from app.dsh_runtime.conversation.repository import MessageSequenceConflict

TENANT = "tenant-a"
OTHER_TENANT = "tenant-b"
OWNER = "user-owner"
PARTICIPANT = "user-participant"


def _repo(harness):
    return ConversationRepository(harness.db)


def _seed_message(harness, session, *, user_id: str, seq: int, message_id, role: str = "user", content: str = "seeded"):
    async def seed():
        await harness.db.chat_messages.insert_one(
            {
                "session_id": session["_id"],
                "user_id": user_id,
                "main_id": TENANT,
                "seq": seq,
                "message_id": message_id,
                "role": role,
                "content": content,
            }
        )

    harness.run(seed())


class _LegacyRacingInsertProxy:
    """Forces a deterministic seq-slot collision: every insert_one first
    persists a legacy-shaped row with the SAME (main_id, session_id, seq) but
    ``message_id=None`` (the legacy writer's shape — it escapes the partial
    unique_string_message_id index), then delegates to the real collection.
    No sleeps, no timing dependence."""

    def __init__(self, real: Any) -> None:
        self._real = real

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)

    async def insert_one(self, document, *args, **kwargs):
        racing = dict(document)
        racing["message_id"] = None
        await self._real.insert_one(racing, *args, **kwargs)
        return await self._real.insert_one(document, *args, **kwargs)


# ---------------------------------------------------------------------------
# Preserved behaviour (passed on the unchanged code, stays green)
# ---------------------------------------------------------------------------


def test_owner_append_updates_the_session_tail(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    session = harness.run(repo.create(tenant_id=TENANT, user_id=OWNER, title="Chat"))
    before = harness.run(harness.db.chat_sessions.find_one({"_id": session["_id"]}))

    doc = harness.run(
        repo.append_message(
            conversation_id=str(session["_id"]),
            tenant_id=TENANT,
            user_id=OWNER,
            role="user",
            content="hello from the owner",
            message_id="msg-o1",
        )
    )

    assert doc["user_id"] == OWNER
    assert doc["seq"] == 1
    after = harness.run(harness.db.chat_sessions.find_one({"_id": session["_id"]}))
    assert after["message_count"] == 1
    assert after["last_message_preview"] == "hello from the owner"
    assert after["last_message_at"] is not None
    assert after["updated_at"] > before["updated_at"]


def test_append_keeps_the_author_integrity_guard(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    session = harness.run(repo.create(tenant_id=TENANT, user_id=OWNER, title="Chat"))
    _seed_message(harness, session, user_id=PARTICIPANT, seq=1, message_id="msg-taken", content="taken")

    with pytest.raises(ValueError):
        harness.run(
            repo.append_message(
                conversation_id=str(session["_id"]),
                tenant_id=TENANT,
                user_id=OWNER,
                role="user",
                content="collision",
                message_id="msg-taken",
            )
        )


def test_append_from_outside_the_tenant_raises_lookup_error(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    session = harness.run(repo.create(tenant_id=TENANT, user_id=OWNER, title="Chat"))

    with pytest.raises(LookupError):
        harness.run(
            repo.append_message(
                conversation_id=str(session["_id"]),
                tenant_id=OTHER_TENANT,
                user_id=PARTICIPANT,
                role="user",
                content="cross tenant",
                message_id="msg-x",
            )
        )
    # The failed lookup happens before any write: no message row exists.
    assert harness.run(harness.db.chat_messages.count_documents({})) == 0


def test_owned_is_retained_for_owner_only_operations(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    session = harness.run(repo.create(tenant_id=TENANT, user_id=OWNER, title="Chat"))

    row = harness.run(repo.owned(str(session["_id"]), tenant_id=TENANT, user_id=OWNER))
    assert str(row["_id"]) == str(session["_id"])
    with pytest.raises(LookupError):
        harness.run(repo.owned(str(session["_id"]), tenant_id=TENANT, user_id=PARTICIPANT))


def test_counter_seeding_preserves_the_normal_increment(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    harness.run(repo.ensure_indexes())
    session = harness.run(repo.create(tenant_id=TENANT, user_id=OWNER, title="Chat"))
    _seed_message(harness, session, user_id=OWNER, seq=5, message_id=None)
    harness.run(
        harness.db.chat_sessions.update_one(
            {"_id": session["_id"]}, {"$set": {"next_message_seq": 5}}
        )
    )

    doc = harness.run(
        repo.append_message(
            conversation_id=str(session["_id"]),
            tenant_id=TENANT,
            user_id=OWNER,
            role="user",
            content="next turn",
            message_id="msg-n1",
        )
    )

    assert doc["seq"] == 6


def test_concurrent_same_message_id_appends_both_return_a_row(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    harness.run(repo.ensure_indexes())
    session = harness.run(repo.create(tenant_id=TENANT, user_id=OWNER, title="Chat"))

    async def scenario():
        return await asyncio.gather(
            repo.append_message(
                conversation_id=str(session["_id"]),
                tenant_id=TENANT,
                user_id=OWNER,
                role="user",
                content="from owner",
                message_id="msg-race",
            ),
            repo.append_message(
                conversation_id=str(session["_id"]),
                tenant_id=TENANT,
                user_id=OWNER,
                role="assistant",
                content="from owner, retried",
                message_id="msg-race",
            ),
        )

    first, second = harness.run(scenario())
    # The loser returns the winner's row (typed idempotent outcome): the
    # DuplicateKeyError never escapes as an unmapped 500.
    assert first["message_id"] == "msg-race"
    assert second["message_id"] == "msg-race"
    assert first["_id"] == second["_id"]


# ---------------------------------------------------------------------------
# New behaviour (RED on the unchanged code)
# ---------------------------------------------------------------------------


def test_participant_append_is_accepted_and_attributed_to_the_participant(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    session = harness.run(repo.create(tenant_id=TENANT, user_id=OWNER, title="Chat"))

    doc = harness.run(
        repo.append_message(
            conversation_id=str(session["_id"]),
            tenant_id=TENANT,
            user_id=PARTICIPANT,
            role="user",
            content="hello from the participant",
            message_id="msg-p1",
        )
    )

    assert doc["user_id"] == PARTICIPANT
    assert doc["seq"] == 1
    assert str(doc["session_id"]) == str(session["_id"])


def test_participant_append_updates_the_session_tail_projection(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    session = harness.run(repo.create(tenant_id=TENANT, user_id=OWNER, title="Chat"))
    before = harness.run(harness.db.chat_sessions.find_one({"_id": session["_id"]}))

    harness.run(
        repo.append_message(
            conversation_id=str(session["_id"]),
            tenant_id=TENANT,
            user_id=PARTICIPANT,
            role="user",
            content="hello from the participant",
            message_id="msg-p1",
        )
    )

    after = harness.run(harness.db.chat_sessions.find_one({"_id": session["_id"]}))
    # The tail projection is scoped by {_id, main_id}: a participant-authored
    # message must not freeze the session tail.
    assert after["message_count"] == 1
    assert after["last_message_preview"] == "hello from the participant"
    assert after["last_message_at"] is not None
    assert after["updated_at"] > before["updated_at"]


def test_message_read_drops_the_viewer_filter(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    session = harness.run(repo.create(tenant_id=TENANT, user_id=OWNER, title="Chat"))
    _seed_message(harness, session, user_id=PARTICIPANT, seq=1, message_id="msg-1")

    row = harness.run(repo.message("msg-1", tenant_id=TENANT, user_id=OWNER))

    assert row is not None
    assert row["user_id"] == PARTICIPANT


def test_message_read_still_scopes_by_tenant(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    session = harness.run(repo.create(tenant_id=TENANT, user_id=OWNER, title="Chat"))
    _seed_message(harness, session, user_id=PARTICIPANT, seq=1, message_id="msg-1")

    assert harness.run(repo.message("msg-1", tenant_id=OTHER_TENANT, user_id=PARTICIPANT)) is None


def test_list_messages_reads_owner_and_participant_messages_in_seq_order(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    session = harness.run(repo.create(tenant_id=TENANT, user_id=OWNER, title="Chat"))
    harness.run(
        repo.append_message(
            conversation_id=str(session["_id"]),
            tenant_id=TENANT,
            user_id=OWNER,
            role="user",
            content="from owner",
            message_id="msg-o1",
        )
    )
    harness.run(
        repo.append_message(
            conversation_id=str(session["_id"]),
            tenant_id=TENANT,
            user_id=PARTICIPANT,
            role="user",
            content="from participant",
            message_id="msg-p1",
        )
    )

    rows = harness.run(repo.list_messages(TENANT, str(session["_id"])))

    assert [(r["seq"], r["user_id"], r["content"]) for r in rows] == [
        (1, OWNER, "from owner"),
        (2, PARTICIPANT, "from participant"),
    ]


def test_list_messages_after_seq_filters_earlier_rows(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    session = harness.run(repo.create(tenant_id=TENANT, user_id=OWNER, title="Chat"))
    for i in range(1, 4):
        _seed_message(harness, session, user_id=OWNER, seq=i, message_id=f"msg-{i}")

    rows = harness.run(repo.list_messages(TENANT, str(session["_id"]), after_seq=1))

    assert [r["seq"] for r in rows] == [2, 3]
    rows_all = harness.run(repo.list_messages(TENANT, str(session["_id"])))
    assert [r["seq"] for r in rows_all] == [1, 2, 3]


def test_list_messages_rejects_an_invalid_conversation_id(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)

    with pytest.raises(LookupError):
        harness.run(repo.list_messages(TENANT, "not-an-objectid"))


def test_counter_seeding_continues_from_a_drifted_max_seq(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    harness.run(repo.ensure_indexes())
    session = harness.run(repo.create(tenant_id=TENANT, user_id=OWNER, title="Chat"))

    async def seed_legacy():
        # Legacy writers minted seq = max(seq)+1 without ever advancing
        # next_message_seq (still 0 on the session doc).
        for i in range(1, 6):
            await harness.db.chat_messages.insert_one(
                {
                    "session_id": session["_id"],
                    "user_id": OWNER,
                    "main_id": TENANT,
                    "seq": i,
                    "message_id": None,
                    "role": "user",
                    "content": f"legacy {i}",
                }
            )

    harness.run(seed_legacy())

    doc = harness.run(
        repo.append_message(
            conversation_id=str(session["_id"]),
            tenant_id=TENANT,
            user_id=OWNER,
            role="user",
            content="first dsh turn",
            message_id="msg-dsh-1",
        )
    )

    # The minted seq continues from the drifted max (6 = 5 + 1), never from
    # the zero counter (1) - no DuplicateKeyError.
    assert doc["seq"] == 6
    after = harness.run(harness.db.chat_sessions.find_one({"_id": session["_id"]}))
    assert after["next_message_seq"] == 6
    rows = harness.run(repo.list_messages(TENANT, str(session["_id"])))
    assert [r["seq"] for r in rows] == [1, 2, 3, 4, 5, 6]


def test_seq_collision_raises_a_typed_conflict_not_a_raw_duplicate_key_error(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    harness.run(repo.ensure_indexes())
    session = harness.run(repo.create(tenant_id=TENANT, user_id=OWNER, title="Chat"))
    repo._messages = _LegacyRacingInsertProxy(repo._messages)

    with pytest.raises(MessageSequenceConflict) as excinfo:
        harness.run(
            repo.append_message(
                conversation_id=str(session["_id"]),
                tenant_id=TENANT,
                user_id=OWNER,
                role="user",
                content="racing the seq slot",
                message_id="msg-race-seq",
            )
        )

    assert excinfo.value.code == "message_sequence_conflict"


def test_mark_active_run_works_for_a_participant(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    session = harness.run(repo.create(tenant_id=TENANT, user_id=OWNER, title="Chat"))

    harness.run(
        repo.mark_active_run(
            conversation_id=str(session["_id"]),
            tenant_id=TENANT,
            user_id=PARTICIPANT,
            message_id="msg-p1",
            run_id="run-p1",
        )
    )

    after = harness.run(harness.db.chat_sessions.find_one({"_id": session["_id"]}))
    assert (after.get("active_run") or {}).get("run_id") == "run-p1"
    assert (after.get("active_run") or {}).get("message_id") == "msg-p1"


def test_clear_active_run_with_a_non_owner_id_still_clears(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    session = harness.run(repo.create(tenant_id=TENANT, user_id=OWNER, title="Chat"))
    harness.run(
        repo.mark_active_run(
            conversation_id=str(session["_id"]),
            tenant_id=TENANT,
            user_id=OWNER,
            message_id="msg-1",
            run_id="run-1",
        )
    )

    harness.run(
        repo.clear_active_run(
            conversation_id=str(session["_id"]),
            tenant_id=TENANT,
            user_id=PARTICIPANT,
            message_id="msg-1",
        )
    )

    after = harness.run(harness.db.chat_sessions.find_one({"_id": session["_id"]}))
    assert after.get("active_run") is None


def test_suspend_active_run_with_a_non_owner_id_still_takes_effect(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    session = harness.run(repo.create(tenant_id=TENANT, user_id=OWNER, title="Chat"))
    harness.run(
        repo.mark_active_run(
            conversation_id=str(session["_id"]),
            tenant_id=TENANT,
            user_id=OWNER,
            message_id="msg-1",
            run_id="run-1",
        )
    )

    harness.run(
        repo.suspend_active_run(
            conversation_id=str(session["_id"]),
            tenant_id=TENANT,
            user_id=PARTICIPANT,
            message_id="msg-1",
            intervention={"suspension_id": "susp-1", "node_id": "node-1", "reason": "approval"},
        )
    )

    after = harness.run(harness.db.chat_sessions.find_one({"_id": session["_id"]}))
    assert after["active_run"]["status"] == "suspended"
    assert after["active_run"]["suspension_id"] == "susp-1"


def test_set_pending_approval_count_with_a_non_owner_id_still_takes_effect(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    session = harness.run(repo.create(tenant_id=TENANT, user_id=OWNER, title="Chat"))

    harness.run(
        repo.set_pending_approval_count(
            conversation_id=str(session["_id"]),
            tenant_id=TENANT,
            user_id=PARTICIPANT,
            count=2,
        )
    )

    after = harness.run(harness.db.chat_sessions.find_one({"_id": session["_id"]}))
    assert after.get("pending_approval_count") == 2


def test_update_assistant_projection_succeeds_when_the_author_differs_from_the_caller(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    session = harness.run(repo.create(tenant_id=TENANT, user_id=OWNER, title="Chat"))
    _seed_message(harness, session, user_id=PARTICIPANT, seq=1, message_id="msg-1", role="assistant", content="draft")

    # The finalizer calls with the binding subject; the author may differ.
    harness.run(
        repo.update_assistant_projection(
            message_id="msg-1",
            tenant_id=TENANT,
            user_id=OWNER,
            content="final answer",
            execution_events=[{"kind": "done"}],
            evidence_bundles=[{"id": "b-1"}],
        )
    )

    row = harness.run(repo.message("msg-1", tenant_id=TENANT, user_id=OWNER))
    assert row["content"] == "final answer"
    assert row["execution_events"] == [{"kind": "done"}]
    assert row["evidence_bundles"] == [{"id": "b-1"}]
