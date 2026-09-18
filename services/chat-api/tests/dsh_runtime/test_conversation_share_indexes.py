"""Real-mongod coverage for the session share fields and the startup index registration."""

from __future__ import annotations

import datetime

import pytest
from pymongo.errors import DuplicateKeyError

from app.dsh_runtime.conversation import ConversationRepository
from app.dsh_runtime.conversation.repository import (
    UNIQUE_MESSAGE_SEQ_INDEX_NAME,
    MessageSequenceIndexConflict,
)

TENANT = "tenant-a"
OTHER_TENANT = "tenant-b"
SHARE_HASH = "a" * 64


def _repo(harness):
    return ConversationRepository(harness.db)


def test_create_initialises_share_fields_to_none(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)

    row = harness.run(repo.create(tenant_id=TENANT, user_id="user-1", title="Chat"))

    assert row["share_token_hash"] is None
    assert row["share_expires_at"] is None
    assert row["share_revoked_at"] is None


def test_ensure_indexes_creates_share_and_sequence_indexes(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)

    harness.run(repo.ensure_indexes())

    session_indexes = harness.run(harness.db.chat_sessions.index_information())
    share_index = session_indexes["unique_main_share_token_hash"]
    assert share_index["key"] == [("main_id", 1), ("share_token_hash", 1)]
    assert share_index["unique"] is True
    assert share_index["partialFilterExpression"] == {
        "share_token_hash": {"$type": "string"}
    }

    message_indexes = harness.run(harness.db.chat_messages.index_information())
    seq_index = message_indexes[UNIQUE_MESSAGE_SEQ_INDEX_NAME]
    assert seq_index["key"] == [("main_id", 1), ("session_id", 1), ("seq", 1)]
    assert seq_index["unique"] is True


def test_never_shared_sessions_do_not_collide_on_the_share_index(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    harness.run(repo.ensure_indexes())

    async def scenario():
        await repo.create(tenant_id=TENANT, user_id="user-1", title="First")
        await repo.create(tenant_id=TENANT, user_id="user-1", title="Second")
        return await harness.db.chat_sessions.count_documents({"main_id": TENANT})

    # The partial filter keeps None (never shared) out of the unique index:
    # a plain unique (main_id, share_token_hash) would reject the second create.
    assert harness.run(scenario()) == 2


def test_two_sessions_in_one_tenant_cannot_hold_the_same_share_token_hash(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    harness.run(repo.ensure_indexes())

    async def scenario():
        first = await repo.create(tenant_id=TENANT, user_id="user-1", title="First")
        second = await repo.create(tenant_id=TENANT, user_id="user-2", title="Second")
        await harness.db.chat_sessions.update_one(
            {"_id": first["_id"]}, {"$set": {"share_token_hash": SHARE_HASH}}
        )
        await harness.db.chat_sessions.update_one(
            {"_id": second["_id"]}, {"$set": {"share_token_hash": SHARE_HASH}}
        )

    with pytest.raises(DuplicateKeyError) as excinfo:
        harness.run(scenario())
    assert "unique_main_share_token_hash" in str(excinfo.value)


def test_same_share_token_hash_is_allowed_across_tenants(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    harness.run(repo.ensure_indexes())

    async def scenario():
        mine = await repo.create(tenant_id=TENANT, user_id="user-1", title="Mine")
        theirs = await repo.create(
            tenant_id=OTHER_TENANT, user_id="user-1", title="Theirs"
        )
        await harness.db.chat_sessions.update_one(
            {"_id": mine["_id"]}, {"$set": {"share_token_hash": SHARE_HASH}}
        )
        await harness.db.chat_sessions.update_one(
            {"_id": theirs["_id"]}, {"$set": {"share_token_hash": SHARE_HASH}}
        )
        return await harness.db.chat_sessions.count_documents(
            {"share_token_hash": SHARE_HASH}
        )

    # The index is (main_id, share_token_hash): the same hash may live in two tenants.
    assert harness.run(scenario()) == 2


def test_two_messages_in_one_session_cannot_share_a_seq(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    harness.run(repo.ensure_indexes())

    async def scenario():
        session = await repo.create(tenant_id=TENANT, user_id="user-1", title="Chat")
        for message_id, user_id in (("msg-1", "user-1"), ("msg-2", "user-2")):
            await harness.db.chat_messages.insert_one(
                {
                    "session_id": session["_id"],
                    "user_id": user_id,
                    "main_id": TENANT,
                    "seq": 1,
                    "message_id": message_id,
                    "role": "user",
                    "content": "duplicate seq",
                }
            )

    with pytest.raises(DuplicateKeyError) as excinfo:
        harness.run(scenario())
    assert UNIQUE_MESSAGE_SEQ_INDEX_NAME in str(excinfo.value)


def test_seeded_duplicate_aborts_startup_with_reported_offending_rows(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)

    async def seed():
        session = await repo.create(tenant_id=TENANT, user_id="user-1", title="Chat")
        for message_id in ("msg-1", "msg-2"):
            await harness.db.chat_messages.insert_one(
                {
                    "session_id": session["_id"],
                    "user_id": "user-1",
                    "main_id": TENANT,
                    "seq": 1,
                    "message_id": message_id,
                    "role": "user",
                    "content": "duplicate seq",
                }
            )
        return session["_id"]

    session_id = harness.run(seed())

    with pytest.raises(MessageSequenceIndexConflict) as excinfo:
        harness.run(repo.ensure_indexes())

    assert excinfo.value.index_name == UNIQUE_MESSAGE_SEQ_INDEX_NAME
    assert len(excinfo.value.samples) == 1
    sample = excinfo.value.samples[0]
    assert sample["main_id"] == TENANT
    assert sample["session_id"] == str(session_id)
    assert sample["seq"] == 1
    assert sample["count"] == 2
    assert sorted(sample["message_ids"]) == ["msg-1", "msg-2"]
    assert "re-sequence" in str(excinfo.value)

    # Aborted means aborted: the index is never created over duplicate data
    # and never skipped silently.
    message_indexes = harness.run(harness.db.chat_messages.index_information())
    assert UNIQUE_MESSAGE_SEQ_INDEX_NAME not in message_indexes


def test_database_isolation_first_witness(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)

    async def scenario():
        session = await repo.create(tenant_id=TENANT, user_id="user-1", title="Chat")
        await harness.db.chat_sessions.update_one(
            {"_id": session["_id"]}, {"$set": {"share_token_hash": SHARE_HASH}}
        )
        await harness.db.chat_messages.insert_one(
            {
                "session_id": session["_id"],
                "user_id": "user-1",
                "main_id": TENANT,
                "seq": 1,
                "message_id": "msg-iso",
                "role": "user",
                "content": "isolation witness",
            }
        )
        return await harness.db.chat_sessions.count_documents({})

    assert harness.run(scenario()) == 1


def test_database_isolation_second_witness_sees_a_clean_database(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)

    # The previous test's session and message rows must not leak into this
    # test's database.
    assert harness.run(harness.db.chat_sessions.count_documents({})) == 0
    assert harness.run(harness.db.chat_messages.count_documents({})) == 0
