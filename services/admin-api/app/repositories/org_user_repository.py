from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import OperationFailure

from app.core.db import get_db
from app.core.security import hash_password

GROUP_COLLECTION = "admin_account_groups"
ACCOUNT_COLLECTION = "admin_accounts"
logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def ensure_indexes() -> None:
    db = get_db()
    try:
        # Best effort: migrate global unique indexes to tenant scoped indexes.
        try:
            await db[GROUP_COLLECTION].drop_index("code_1")
        except Exception:
            pass
        try:
            await db[ACCOUNT_COLLECTION].drop_index("username_1")
        except Exception:
            pass

        await db[GROUP_COLLECTION].create_index(
            [("main_id", 1), ("code", 1)],
            unique=True,
            name="main_id_code_unique",
        )
        await db[GROUP_COLLECTION].create_index([("main_id", 1), ("status", 1)], name="group_main_id_status")
        await db[ACCOUNT_COLLECTION].create_index(
            [("main_id", 1), ("username", 1)],
            unique=True,
            name="main_id_username_unique",
        )
        await db[ACCOUNT_COLLECTION].create_index(
            [("main_id", 1), ("group_code", 1)],
            name="account_main_id_group_code",
        )
        await db[ACCOUNT_COLLECTION].create_index(
            [("main_id", 1), ("status", 1)],
            name="account_main_id_status",
        )
    except OperationFailure as exc:
        logger.warning("org user index creation skipped: %s", exc)


async def backfill_main_id(default_main_id: str) -> None:
    db = get_db()
    now = utcnow()
    await db[GROUP_COLLECTION].update_many(
        {"main_id": {"$exists": False}},
        {"$set": {"main_id": default_main_id, "updated_at": now}},
    )
    await db[ACCOUNT_COLLECTION].update_many(
        {"main_id": {"$exists": False}},
        {"$set": {"main_id": default_main_id, "updated_at": now}},
    )


async def list_account_groups(main_id: str) -> list[dict]:
    db = get_db()
    cursor = db[GROUP_COLLECTION].find({"main_id": main_id}).sort("updated_at", -1)
    return await cursor.to_list(length=200)


async def find_group_by_code(code: str, main_id: str) -> dict | None:
    db = get_db()
    return await db[GROUP_COLLECTION].find_one({"code": code, "main_id": main_id})


async def find_group_by_id(group_id: str, main_id: str) -> dict | None:
    db = get_db()
    return await db[GROUP_COLLECTION].find_one({"_id": ObjectId(group_id), "main_id": main_id})


async def create_account_group(payload: dict) -> dict:
    db = get_db()
    now = utcnow()
    main_id = payload["main_id"]
    base_code = _normalize_group_code(payload["name"])
    code = await _next_available_group_code(base_code, main_id)
    doc = {
        "main_id": main_id,
        "name": payload["name"],
        "code": code,
        "description": payload.get("description") or "",
        "status": payload.get("status") or "active",
        "created_at": now,
        "updated_at": now,
    }
    result = await db[GROUP_COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def update_account_group(group_id: str, payload: dict) -> bool:
    db = get_db()
    result = await db[GROUP_COLLECTION].update_one(
        {"_id": ObjectId(group_id), "main_id": payload["main_id"]},
        {
            "$set": {
                "name": payload["name"],
                "description": payload.get("description") or "",
                "status": payload.get("status") or "active",
                "updated_at": utcnow(),
            }
        },
    )
    return result.matched_count > 0


async def delete_account_group(group_id: str, main_id: str) -> bool:
    db = get_db()
    group = await db[GROUP_COLLECTION].find_one({"_id": ObjectId(group_id), "main_id": main_id})
    if group is None:
        return False
    in_use_count = await db[ACCOUNT_COLLECTION].count_documents({"group_code": group["code"], "main_id": main_id})
    if in_use_count > 0:
        raise ValueError("账号组下仍有账号，无法删除")
    result = await db[GROUP_COLLECTION].delete_one({"_id": ObjectId(group_id), "main_id": main_id})
    return result.deleted_count > 0


async def count_accounts_by_group_code(group_code: str, main_id: str) -> int:
    db = get_db()
    return await db[ACCOUNT_COLLECTION].count_documents({"group_code": group_code, "main_id": main_id})


async def list_accounts(main_id: str) -> list[dict]:
    db = get_db()
    cursor = db[ACCOUNT_COLLECTION].find({"main_id": main_id}).sort("updated_at", -1)
    return await cursor.to_list(length=1000)


async def find_account_by_username(username: str, main_id: str) -> dict | None:
    db = get_db()
    return await db[ACCOUNT_COLLECTION].find_one({"username": username, "main_id": main_id})


async def find_account_by_username_any_main(username: str) -> dict | None:
    db = get_db()
    rows = await db[ACCOUNT_COLLECTION].find({"username": username}).limit(2).to_list(length=2)
    if len(rows) == 1:
        return rows[0]
    return None


async def list_accounts_by_username(username: str) -> list[dict]:
    db = get_db()
    cursor = db[ACCOUNT_COLLECTION].find({"username": username}).sort([("updated_at", -1)])
    return await cursor.to_list(length=100)


async def find_account_by_id(account_id: str, main_id: str) -> dict | None:
    db = get_db()
    return await db[ACCOUNT_COLLECTION].find_one({"_id": ObjectId(account_id), "main_id": main_id})


async def create_account(payload: dict) -> dict:
    db = get_db()
    now = utcnow()
    password_hash, password_salt = hash_password(payload.get("password") or "")
    doc = {
        "main_id": payload["main_id"],
        "username": payload["username"],
        "display_name": payload["display_name"],
        "email": payload.get("email") or "",
        "phone": payload.get("phone") or "",
        "group_code": payload["group_code"],
        "role_name": payload["role_name"],
        "status": payload.get("status") or "active",
        "password_hash": password_hash,
        "password_salt": password_salt,
        "is_protected": bool(payload.get("is_protected", False)),
        "last_login_at": None,
        "created_at": now,
        "updated_at": now,
    }
    result = await db[ACCOUNT_COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def update_account(account_id: str, payload: dict) -> bool:
    db = get_db()
    result = await db[ACCOUNT_COLLECTION].update_one(
        {"_id": ObjectId(account_id), "main_id": payload["main_id"]},
        {
            "$set": {
                "display_name": payload["display_name"],
                "email": payload.get("email") or "",
                "phone": payload.get("phone") or "",
                "group_code": payload["group_code"],
                "role_name": payload["role_name"],
                "status": payload.get("status") or "active",
                "updated_at": utcnow(),
            }
        },
    )
    return result.matched_count > 0


async def delete_account(account_id: str, main_id: str) -> bool:
    db = get_db()
    account = await db[ACCOUNT_COLLECTION].find_one({"_id": ObjectId(account_id), "main_id": main_id})
    if account is None:
        return False
    if bool(account.get("is_protected", False)):
        raise ValueError("系统内置账号不可删除")
    result = await db[ACCOUNT_COLLECTION].delete_one({"_id": ObjectId(account_id), "main_id": main_id})
    return result.deleted_count > 0


async def touch_account_last_login(username: str, main_id: str) -> None:
    db = get_db()
    now = utcnow()
    await db[ACCOUNT_COLLECTION].update_one(
        {"username": username, "main_id": main_id},
        {"$set": {"last_login_at": now, "updated_at": now}},
    )


async def set_account_password(username: str, password: str, main_id: str) -> None:
    db = get_db()
    now = utcnow()
    password_hash, password_salt = hash_password(password)
    await db[ACCOUNT_COLLECTION].update_one(
        {"username": username, "main_id": main_id},
        {
            "$set": {
                "password_hash": password_hash,
                "password_salt": password_salt,
                "updated_at": now,
            }
        },
    )


async def update_account_profile(username: str, main_id: str, payload: dict) -> dict | None:
    db = get_db()
    now = utcnow()
    result = await db[ACCOUNT_COLLECTION].find_one_and_update(
        {"username": username, "main_id": main_id},
        {
            "$set": {
                "display_name": payload["display_name"],
                "email": payload.get("email") or "",
                "phone": payload.get("phone") or "",
                "updated_at": now,
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    return result


async def update_account_avatar(username: str, main_id: str, avatar_url: str) -> dict | None:
    db = get_db()
    now = utcnow()
    result = await db[ACCOUNT_COLLECTION].find_one_and_update(
        {"username": username, "main_id": main_id},
        {
            "$set": {
                "avatar_url": avatar_url,
                "avatar_updated_at": now,
                "updated_at": now,
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    return result


async def ensure_group_exists(name: str, code: str, main_id: str, description: str = "") -> None:
    db = get_db()
    now = utcnow()
    await db[GROUP_COLLECTION].update_one(
        {"code": code, "main_id": main_id},
        {
            "$setOnInsert": {
                "main_id": main_id,
                "name": name,
                "code": code,
                "description": description,
                "status": "active",
                "created_at": now,
            },
            "$set": {"updated_at": now},
        },
        upsert=True,
    )


async def ensure_bootstrap_account(
    main_id: str,
    username: str,
    password: str,
    display_name: str,
    role_name: str,
    org_name: str,
    group_code: str,
) -> None:
    db = get_db()
    now = utcnow()
    existing = await db[ACCOUNT_COLLECTION].find_one({"username": username, "main_id": main_id})
    if existing is None:
        password_hash, password_salt = hash_password(password)
        await db[ACCOUNT_COLLECTION].insert_one(
            {
                "main_id": main_id,
                "username": username,
                "display_name": display_name,
                "email": "",
                "phone": "",
                "group_code": group_code,
                "role_name": role_name,
                "org_name": org_name,
                "status": "active",
                "is_protected": True,
                "password_hash": password_hash,
                "password_salt": password_salt,
                "last_login_at": None,
                "created_at": now,
                "updated_at": now,
            }
        )
        return
    update_doc: dict[str, object] = {
        "display_name": display_name,
        "group_code": existing.get("group_code") or group_code,
        "role_name": role_name,
        "org_name": org_name,
        "status": "active",
        "is_protected": True,
        "updated_at": now,
    }
    if not existing.get("password_hash") or not existing.get("password_salt"):
        password_hash, password_salt = hash_password(password)
        update_doc["password_hash"] = password_hash
        update_doc["password_salt"] = password_salt
    await db[ACCOUNT_COLLECTION].update_one(
        {"username": username, "main_id": main_id},
        {"$set": update_doc},
    )


async def count_accounts(main_id: str) -> int:
    db = get_db()
    return await db[ACCOUNT_COLLECTION].count_documents({"main_id": main_id})


def _normalize_group_code(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().lower()).strip("_")
    return cleaned or "group"


async def _next_available_group_code(base_code: str, main_id: str) -> str:
    code = base_code
    suffix = 1
    while await find_group_by_code(code, main_id):
        suffix += 1
        code = f"{base_code}_{suffix}"
    return code
