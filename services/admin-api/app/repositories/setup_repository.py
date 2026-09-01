from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.db import get_db

SETUP_COLLECTION = "system_bootstrap"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def ensure_indexes() -> None:
    db = get_db()
    await db[SETUP_COLLECTION].create_index([("completed", 1)], name="setup_completed")
    await db[SETUP_COLLECTION].create_index([("main_id", 1)], unique=True, sparse=True, name="setup_main_id_unique")


async def get_setup_state() -> dict[str, Any] | None:
    db = get_db()
    return await db[SETUP_COLLECTION].find_one({"_id": "singleton"})


async def mark_setup_completed(*, main_id: str, org_name: str, admin_username: str, employee_username: str) -> None:
    db = get_db()
    now = utcnow()
    await db[SETUP_COLLECTION].update_one(
        {"_id": "singleton"},
        {
            "$set": {
                "completed": True,
                "main_id": main_id,
                "org_name": org_name,
                "admin_username": admin_username,
                "employee_username": employee_username,
                "updated_at": now,
            },
            "$setOnInsert": {
                "created_at": now,
            },
        },
        upsert=True,
    )
