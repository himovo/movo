from __future__ import annotations

from datetime import datetime, timezone

from pymongo.errors import OperationFailure

from app.core.db import get_db

DEPARTMENT_COLLECTION = "org_units"
USER_COLLECTION = "end_users"
USER_ORG_REL_COLLECTION = "end_user_org_relations"
USER_FIELD_DEF_COLLECTION = "user_field_defs"
USER_FIELD_VALUE_COLLECTION = "user_field_values"
USER_IDENTITY_COLLECTION = "user_identities"
USER_INVITE_COLLECTION = "user_invites"
AUDIT_LOG_COLLECTION = "audit_logs"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def ensure_indexes() -> None:
    db = get_db()
    try:
        await db[DEPARTMENT_COLLECTION].create_index([("main_id", 1), ("code", 1)], unique=True, name="dept_main_code_unique")
        await db[DEPARTMENT_COLLECTION].create_index([("main_id", 1), ("parent_id", 1)], name="dept_main_parent")
        await db[DEPARTMENT_COLLECTION].create_index([("main_id", 1), ("status", 1)], name="dept_main_status")
        await db[USER_COLLECTION].create_index([("main_id", 1), ("name", 1)], name="user_main_name")
        await db[USER_COLLECTION].create_index([("main_id", 1), ("mobile", 1)], name="user_main_mobile")
        await db[USER_COLLECTION].create_index([("main_id", 1), ("email", 1)], name="user_main_email")
        try:
            await db[USER_COLLECTION].drop_index("user_main_login_name_unique")
        except Exception:
            pass
        now = utcnow()
        await db[USER_COLLECTION].update_many(
            {"login_name": ""},
            {"$unset": {"login_name": ""}, "$set": {"updated_at": now}},
        )
        await db[USER_COLLECTION].update_many(
            {"login_name": {"$type": "null"}},
            {"$unset": {"login_name": ""}, "$set": {"updated_at": now}},
        )
        await db[USER_COLLECTION].create_index(
            [("main_id", 1), ("login_name", 1)],
            unique=True,
            name="user_main_login_name_unique",
            partialFilterExpression={"login_name": {"$exists": True, "$type": "string"}},
        )
        await db[USER_ORG_REL_COLLECTION].create_index(
            [("main_id", 1), ("user_id", 1), ("org_id", 1)],
            unique=True,
            name="user_org_rel_unique",
        )
        await db[USER_ORG_REL_COLLECTION].create_index([("main_id", 1), ("org_id", 1)], name="user_org_rel_org")
        await db[USER_FIELD_DEF_COLLECTION].create_index([("main_id", 1), ("field_key", 1)], unique=True, name="field_def_unique")
        await db[USER_FIELD_VALUE_COLLECTION].create_index(
            [("main_id", 1), ("user_id", 1), ("field_key", 1)],
            unique=True,
            name="field_value_unique",
        )
        await db[USER_IDENTITY_COLLECTION].create_index(
            [("main_id", 1), ("provider", 1), ("provider_user_id", 1)],
            unique=True,
            name="identity_provider_user_unique",
        )
        await db[USER_IDENTITY_COLLECTION].create_index([("main_id", 1), ("user_id", 1)], name="identity_user")
        await db[USER_INVITE_COLLECTION].create_index([("main_id", 1), ("token", 1)], unique=True, name="user_invite_token_unique")
        await db[USER_INVITE_COLLECTION].create_index([("main_id", 1), ("user_id", 1), ("created_at", -1)], name="user_invite_user_created")
        await db[USER_INVITE_COLLECTION].create_index([("expires_at", 1)], expireAfterSeconds=0, name="user_invite_expires_ttl")
        await db[AUDIT_LOG_COLLECTION].create_index([("main_id", 1), ("created_at", -1)], name="audit_main_created")
    except OperationFailure:
        # Keep startup resilient when db account has restricted index permissions.
        return


async def ensure_root_department(main_id: str) -> None:
    db = get_db()
    now = utcnow()
    await db[DEPARTMENT_COLLECTION].update_one(
        {"main_id": main_id, "code": "root"},
        {
            "$setOnInsert": {
                "main_id": main_id,
                "name": "企业总部",
                "code": "root",
                "parent_id": None,
                "path_ids": [],
                "path_names": [],
                "status": "active",
                "source": "local",
                "source_dept_id": "",
                "created_at": now,
            },
            "$set": {"updated_at": now},
        },
        upsert=True,
    )
