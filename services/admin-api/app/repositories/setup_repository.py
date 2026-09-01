from __future__ import annotations

from datetime import datetime, timezone
from datetime import timedelta
from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.db import get_db

SETUP_COLLECTION = "system_bootstrap"
SETUP_LOCK_TTL = timedelta(minutes=15)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def ensure_indexes() -> None:
    db = get_db()
    await db[SETUP_COLLECTION].create_index([("completed", 1)], name="setup_completed")
    await db[SETUP_COLLECTION].create_index([("main_id", 1)], unique=True, sparse=True, name="setup_main_id_unique")


async def get_setup_state() -> dict[str, Any] | None:
    db = get_db()
    return await db[SETUP_COLLECTION].find_one({"_id": "singleton"})


async def acquire_setup_lock(lock_token: str) -> bool:
    """Claim the one-time initializer across processes using MongoDB CAS."""

    db = get_db()
    now = utcnow()
    try:
        state = await db[SETUP_COLLECTION].find_one_and_update(
            {
                "_id": "singleton",
                "completed": {"$ne": True},
                "$or": [
                    {"lock_token": {"$exists": False}},
                    {"lock_expires_at": {"$lte": now}},
                ],
            },
            {
                "$set": {
                    "lock_token": lock_token,
                    "lock_acquired_at": now,
                    "lock_expires_at": now + SETUP_LOCK_TTL,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now, "completed": False},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        return False
    return bool(state and state.get("lock_token") == lock_token)


async def release_setup_lock(lock_token: str) -> None:
    db = get_db()
    await db[SETUP_COLLECTION].update_one(
        {"_id": "singleton", "lock_token": lock_token, "completed": {"$ne": True}},
        {"$unset": {"lock_token": "", "lock_acquired_at": "", "lock_expires_at": ""}},
    )


async def mark_setup_completed(
    *,
    lock_token: str,
    main_id: str,
    org_name: str,
    admin_username: str,
    employee_username: str,
) -> None:
    db = get_db()
    now = utcnow()
    result = await db[SETUP_COLLECTION].update_one(
        {"_id": "singleton", "lock_token": lock_token, "completed": {"$ne": True}},
        {
            "$set": {
                "completed": True,
                "main_id": main_id,
                "org_name": org_name,
                "admin_username": admin_username,
                "employee_username": employee_username,
                "updated_at": now,
            },
            "$unset": {"lock_token": "", "lock_acquired_at": "", "lock_expires_at": ""},
        },
    )
    if result.modified_count != 1:
        raise RuntimeError("setup initialization lock was lost before completion")
