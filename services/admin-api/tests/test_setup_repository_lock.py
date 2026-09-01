from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pymongo.errors import DuplicateKeyError

from app.repositories import setup_repository


def _database(collection):
    class Database:
        def __getitem__(self, name):
            assert name == setup_repository.SETUP_COLLECTION
            return collection

    return Database()


def test_setup_lock_is_acquired_with_one_atomic_write(monkeypatch) -> None:
    collection = SimpleNamespace(
        find_one_and_update=AsyncMock(return_value={"lock_token": "lock-a"}),
    )
    monkeypatch.setattr(setup_repository, "get_db", lambda: _database(collection))

    assert asyncio.run(setup_repository.acquire_setup_lock("lock-a")) is True
    query = collection.find_one_and_update.await_args.args[0]
    assert query["_id"] == "singleton"
    assert query["completed"] == {"$ne": True}
    assert {"lock_token": {"$exists": False}} in query["$or"]


def test_setup_lock_rejects_a_concurrent_initializer(monkeypatch) -> None:
    collection = SimpleNamespace(
        find_one_and_update=AsyncMock(side_effect=DuplicateKeyError("already locked")),
    )
    monkeypatch.setattr(setup_repository, "get_db", lambda: _database(collection))

    assert asyncio.run(setup_repository.acquire_setup_lock("lock-b")) is False


def test_setup_completion_requires_the_owned_lock(monkeypatch) -> None:
    collection = SimpleNamespace(update_one=AsyncMock(return_value=SimpleNamespace(modified_count=0)))
    monkeypatch.setattr(setup_repository, "get_db", lambda: _database(collection))

    with pytest.raises(RuntimeError, match="lock was lost"):
        asyncio.run(
            setup_repository.mark_setup_completed(
                lock_token="lock-c",
                main_id="tenant-a",
                org_name="MOVO",
                admin_username="admin",
                employee_username="employee",
            )
        )
