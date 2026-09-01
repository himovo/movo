from __future__ import annotations

import logging
from datetime import datetime, timezone

from pymongo.errors import OperationFailure

from app.core.db import get_db

COLLECTION_NAME = "admin_sessions"
logger = logging.getLogger(__name__)


async def ensure_indexes() -> None:
    db = get_db()
    try:
        await db[COLLECTION_NAME].create_index("session_id", unique=True)
        await db[COLLECTION_NAME].create_index("username")
        await db[COLLECTION_NAME].create_index("expires_at")
    except OperationFailure as exc:
        logger.warning("admin_sessions index creation skipped: %s", exc)


async def create_session(
    session_id: str,
    username: str,
    token_expires_at: int,
    user_agent: str | None = None,
    ip: str | None = None,
) -> None:
    db = get_db()
    expires_at = datetime.fromtimestamp(token_expires_at, tz=timezone.utc)
    now = datetime.now(timezone.utc)
    await db[COLLECTION_NAME].insert_one(
        {
            "session_id": session_id,
            "username": username,
            "status": "active",
            "user_agent": user_agent,
            "ip": ip,
            "created_at": now,
            "updated_at": now,
            "expires_at": expires_at,
            "revoked_at": None,
        }
    )


async def find_session(session_id: str) -> dict | None:
    db = get_db()
    return await db[COLLECTION_NAME].find_one({"session_id": session_id})


async def revoke_session(session_id: str) -> None:
    db = get_db()
    now = datetime.now(timezone.utc)
    await db[COLLECTION_NAME].update_one(
        {"session_id": session_id},
        {"$set": {"status": "revoked", "revoked_at": now, "updated_at": now}},
    )
