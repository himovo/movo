from __future__ import annotations

import logging
from datetime import datetime, timezone

from pymongo.errors import OperationFailure

from app.core.db import get_db
from app.models.admin_user import AdminUser

COLLECTION_NAME = "admin_users"
logger = logging.getLogger(__name__)


async def ensure_indexes() -> None:
    db = get_db()
    try:
        await db[COLLECTION_NAME].create_index("username", unique=True)
    except OperationFailure as exc:
        logger.warning("admin_users index creation skipped: %s", exc)


async def find_by_username(username: str) -> dict | None:
    db = get_db()
    return await db[COLLECTION_NAME].find_one({"username": username})


async def create_admin_user(user: AdminUser) -> str:
    db = get_db()
    result = await db[COLLECTION_NAME].insert_one(user.to_document())
    return str(result.inserted_id)


async def ensure_bootstrap_admin(user: AdminUser) -> dict:
    existing = await find_by_username(user.username)
    if existing:
        return existing
    await create_admin_user(user)
    created = await find_by_username(user.username)
    if created is None:
        raise RuntimeError("Failed to create bootstrap admin")
    return created


async def touch_last_login(username: str) -> None:
    db = get_db()
    now = datetime.now(timezone.utc)
    await db[COLLECTION_NAME].update_one(
        {"username": username},
        {"$set": {"last_login_at": now, "updated_at": now}},
    )


async def count_admin_users() -> int:
    db = get_db()
    return await db[COLLECTION_NAME].count_documents({})
