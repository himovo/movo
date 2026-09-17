"""Real-mongod coverage for the session participants repository."""

from __future__ import annotations

import asyncio
import datetime

import pytest

from app.dsh_runtime.conversation.participants_repository import (
    SessionParticipantsRepository,
)

TENANT = "tenant-a"
OTHER_TENANT = "tenant-b"


def _repo(harness):
    return SessionParticipantsRepository(harness.db)


def test_ensure_indexes_creates_membership_indexes(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    harness.run(repo.ensure_indexes())

    info = harness.run(harness.db.session_participants.index_information())

    unique = info["unique_conversation_participant"]
    assert unique["key"] == [("conversation_id", 1), ("user_id", 1)]
    assert unique["unique"] is True

    by_user = info["participant_memberships_by_user"]
    assert by_user["key"] == [("main_id", 1), ("user_id", 1), ("joined_at", -1)]


def test_add_twice_yields_exactly_one_row(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    harness.run(repo.ensure_indexes())

    async def scenario():
        await repo.add(tenant_id=TENANT, conversation_id="conv-1", user_id="user-1")
        await repo.add(tenant_id=TENANT, conversation_id="conv-1", user_id="user-1")
        return await repo.list("conv-1", tenant_id=TENANT, include_removed=True)

    rows = harness.run(scenario())
    assert len(rows) == 1
    row = rows[0]
    assert row["main_id"] == TENANT
    assert row["conversation_id"] == "conv-1"
    assert row["user_id"] == "user-1"
    assert row["role"] == "participant"
    assert isinstance(row["joined_at"], datetime.datetime)
    assert row["last_read_seq"] == 0
    assert row["removed_at"] is None


def test_readd_after_remove_reactivates_the_same_row(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    harness.run(repo.ensure_indexes())

    harness.run(repo.add(tenant_id=TENANT, conversation_id="conv-1", user_id="user-1"))
    original_id = harness.run(repo.list("conv-1", tenant_id=TENANT))[0]["_id"]

    harness.run(repo.remove("conv-1", tenant_id=TENANT, user_id="user-1"))
    assert harness.run(repo.is_member("conv-1", tenant_id=TENANT, user_id="user-1")) is False
    assert harness.run(repo.list("conv-1", tenant_id=TENANT)) == []

    harness.run(repo.add(tenant_id=TENANT, conversation_id="conv-1", user_id="user-1"))
    rows = harness.run(repo.list("conv-1", tenant_id=TENANT))
    assert len(rows) == 1
    assert rows[0]["_id"] == original_id
    assert rows[0]["removed_at"] is None


def test_concurrent_adds_yield_exactly_one_row(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    harness.run(repo.ensure_indexes())

    async def scenario():
        await asyncio.gather(
            repo.add(tenant_id=TENANT, conversation_id="conv-1", user_id="user-1"),
            repo.add(tenant_id=TENANT, conversation_id="conv-1", user_id="user-1"),
        )
        return await repo.list("conv-1", tenant_id=TENANT, include_removed=True)

    rows = harness.run(scenario())
    assert len(rows) == 1


def test_is_member_is_true_only_for_active_participant_rows(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    harness.run(repo.ensure_indexes())

    assert harness.run(repo.is_member("conv-1", tenant_id=TENANT, user_id="user-1")) is False

    harness.run(repo.add(tenant_id=TENANT, conversation_id="conv-1", user_id="user-1"))
    assert harness.run(repo.is_member("conv-1", tenant_id=TENANT, user_id="user-1")) is True

    harness.run(repo.remove("conv-1", tenant_id=TENANT, user_id="user-1"))
    assert harness.run(repo.is_member("conv-1", tenant_id=TENANT, user_id="user-1")) is False

    # Tenant scoping: another tenant never sees the row.
    assert harness.run(repo.is_member("conv-1", tenant_id=OTHER_TENANT, user_id="user-1")) is False


def test_membership_states_are_independent_per_tenant(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    harness.run(repo.ensure_indexes())

    async def scenario():
        await repo.add(tenant_id=TENANT, conversation_id="conv-a", user_id="user-1")
        await repo.remove("conv-a", tenant_id=TENANT, user_id="user-1")
        await repo.add(tenant_id=OTHER_TENANT, conversation_id="conv-b", user_id="user-1")
        return [
            await repo.is_member("conv-a", tenant_id=TENANT, user_id="user-1"),
            await repo.is_member("conv-a", tenant_id=OTHER_TENANT, user_id="user-1"),
            await repo.is_member("conv-b", tenant_id=OTHER_TENANT, user_id="user-1"),
            await repo.is_member("conv-b", tenant_id=TENANT, user_id="user-1"),
        ]

    assert harness.run(scenario()) == [False, False, True, False]


def test_list_returns_active_rows_only_unless_all_requested(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    harness.run(repo.ensure_indexes())

    async def scenario():
        await repo.add(tenant_id=TENANT, conversation_id="conv-1", user_id="user-1")
        await repo.add(tenant_id=TENANT, conversation_id="conv-1", user_id="user-2")
        await repo.add(tenant_id=TENANT, conversation_id="conv-1", user_id="user-3")
        await repo.remove("conv-1", tenant_id=TENANT, user_id="user-3")
        active = await repo.list("conv-1", tenant_id=TENANT)
        everything = await repo.list("conv-1", tenant_id=TENANT, include_removed=True)
        return active, everything

    active, everything = harness.run(scenario())
    assert [row["user_id"] for row in active] == ["user-1", "user-2"]
    assert len(everything) == 3


def test_list_for_user_pages_active_memberships_by_joined_at_desc(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    harness.run(repo.ensure_indexes())

    async def scenario():
        await repo.add(tenant_id=TENANT, conversation_id="conv-1", user_id="user-1")
        await repo.add(tenant_id=TENANT, conversation_id="conv-2", user_id="user-1")
        await repo.add(tenant_id=TENANT, conversation_id="conv-3", user_id="user-1")
        await repo.remove("conv-2", tenant_id=TENANT, user_id="user-1")
        page_one = await repo.list_for_user(TENANT, user_id="user-1", limit=1, offset=0)
        page_two = await repo.list_for_user(TENANT, user_id="user-1", limit=1, offset=1)
        page_three = await repo.list_for_user(TENANT, user_id="user-1", limit=1, offset=2)
        return page_one, page_two, page_three

    page_one, page_two, page_three = harness.run(scenario())
    assert [row["conversation_id"] for row in page_one] == ["conv-3"]
    assert [row["conversation_id"] for row in page_two] == ["conv-1"]
    assert page_three == []
    assert page_one[0]["joined_at"] >= page_two[0]["joined_at"]


def test_list_for_user_is_tenant_scoped(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    harness.run(repo.ensure_indexes())

    async def scenario():
        await repo.add(tenant_id=TENANT, conversation_id="conv-1", user_id="user-1")
        await repo.add(tenant_id=OTHER_TENANT, conversation_id="conv-9", user_id="user-1")
        mine = await repo.list_for_user(TENANT, user_id="user-1", limit=10, offset=0)
        theirs = await repo.list_for_user(OTHER_TENANT, user_id="user-1", limit=10, offset=0)
        return mine, theirs

    mine, theirs = harness.run(scenario())
    assert [row["conversation_id"] for row in mine] == ["conv-1"]
    assert [row["conversation_id"] for row in theirs] == ["conv-9"]


def test_set_read_cursor_persists_last_read_seq(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    harness.run(repo.ensure_indexes())

    async def scenario():
        await repo.add(tenant_id=TENANT, conversation_id="conv-1", user_id="user-1")
        await repo.add(tenant_id=TENANT, conversation_id="conv-1", user_id="user-2")
        await repo.set_read_cursor("conv-1", tenant_id=TENANT, user_id="user-1", last_read_seq=7)
        return await repo.list("conv-1", tenant_id=TENANT)

    rows = harness.run(scenario())
    by_user = {row["user_id"]: row for row in rows}
    assert by_user["user-1"]["last_read_seq"] == 7
    assert by_user["user-2"]["last_read_seq"] == 0


def test_delete_for_conversation_removes_all_participant_rows(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    harness.run(repo.ensure_indexes())

    async def scenario():
        await repo.add(tenant_id=TENANT, conversation_id="conv-1", user_id="user-1")
        await repo.add(tenant_id=TENANT, conversation_id="conv-1", user_id="user-2")
        await repo.add(tenant_id=TENANT, conversation_id="conv-2", user_id="user-1")
        await repo.delete_for_conversation("conv-1", tenant_id=TENANT)
        remaining = await repo.list_for_user(TENANT, user_id="user-1", limit=10, offset=0)
        conv_1_rows = await repo.list("conv-1", tenant_id=TENANT, include_removed=True)
        return remaining, conv_1_rows

    remaining, conv_1_rows = harness.run(scenario())
    assert [row["conversation_id"] for row in remaining] == ["conv-2"]
    assert conv_1_rows == []


def test_remove_only_affects_the_target_tenant_row(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    harness.run(repo.ensure_indexes())

    async def scenario():
        await repo.add(tenant_id=TENANT, conversation_id="conv-a", user_id="user-1")
        await repo.add(tenant_id=OTHER_TENANT, conversation_id="conv-b", user_id="user-1")
        await repo.remove("conv-a", tenant_id=TENANT, user_id="user-1")
        mine = await repo.list("conv-a", tenant_id=TENANT, include_removed=True)
        theirs = await repo.list("conv-b", tenant_id=OTHER_TENANT, include_removed=True)
        still_member = await repo.is_member(
            "conv-b", tenant_id=OTHER_TENANT, user_id="user-1"
        )
        return mine, theirs, still_member

    mine, theirs, still_member = harness.run(scenario())
    assert mine[0]["removed_at"] is not None
    assert theirs[0]["removed_at"] is None
    assert still_member is True


def test_database_isolation_first_witness(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    harness.run(repo.ensure_indexes())

    harness.run(repo.add(tenant_id=TENANT, conversation_id="conv-1", user_id="user-1"))
    assert len(harness.run(repo.list("conv-1", tenant_id=TENANT))) == 1


def test_database_isolation_second_witness_sees_a_clean_database(real_mongo_db):
    harness = real_mongo_db
    repo = _repo(harness)
    harness.run(repo.ensure_indexes())

    # The previous test's row must not leak into this test's database.
    assert harness.run(repo.list("conv-1", tenant_id=TENANT, include_removed=True)) == []


def test_fixture_yields_a_real_motor_database(real_mongo_db):
    harness = real_mongo_db
    assert harness.db.name.startswith("movo_test_")
    build_info = harness.run(harness.db.client.admin.command("buildInfo"))
    major, minor = (int(part) for part in build_info["version"].split(".")[:2])
    # partialFilterExpression indexes need MongoDB >= 3.2.
    assert (major, minor) >= (3, 2)
