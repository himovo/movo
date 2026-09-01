from __future__ import annotations

from datetime import datetime

from bson import ObjectId
from fastapi import HTTPException

from app.core.config import get_settings
from app.core.db import get_db
from app.core.end_user_auth import parse_and_verify_session_token
from app.core.tenant import add_main_scope, resolve_main_id


USER_COLLECTION = "end_users"
USER_SESSION_COLLECTION = "end_user_sessions"


def extract_bearer_token(authorization: str | None) -> str:
    raw = str(authorization or "").strip()
    if not raw.lower().startswith("bearer "):
        return ""
    return raw[7:].strip()


async def resolve_session_user(authorization: str | None) -> dict:
    settings = get_settings()
    token_id = parse_and_verify_session_token(
        settings.END_USER_AUTH_SECRET,
        extract_bearer_token(authorization),
    )
    if not token_id:
        raise HTTPException(status_code=401, detail="invalid_token")

    db = get_db()
    session_doc = await db[USER_SESSION_COLLECTION].find_one(
        {"token_id": token_id, "status": "active"}
    )
    if not session_doc:
        raise HTTPException(status_code=401, detail="session_not_found")

    now = datetime.utcnow()
    if session_doc.get("expires_at") and session_doc["expires_at"] < now:
        await db[USER_SESSION_COLLECTION].update_one(
            {"_id": session_doc["_id"]},
            {"$set": {"status": "expired", "updated_at": now}},
        )
        raise HTTPException(status_code=401, detail="session_expired")

    user_id = str(session_doc.get("user_id") or "")
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=401, detail="invalid_session_user")

    main_id = resolve_main_id(session_doc.get("main_id"))
    user_doc = await db[USER_COLLECTION].find_one(
        add_main_scope({"_id": ObjectId(user_id), "status": "active"}, main_id)
    )
    if not user_doc:
        raise HTTPException(status_code=401, detail="user_not_found")

    await db[USER_SESSION_COLLECTION].update_one(
        {"_id": session_doc["_id"]},
        {"$set": {"last_seen_at": now, "updated_at": now}},
    )
    return {"session": session_doc, "user": user_doc, "main_id": main_id}
