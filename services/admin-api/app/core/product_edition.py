from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status

from app.core.db import get_db


COMMUNITY_EDITION = "community"
ORGANIZATION_COLLECTION = "organizations"
SETUP_COLLECTION = "system_bootstrap"
USER_COLLECTION = "end_users"
ORG_QUOTA_COLLECTION = "org_quota_policies"


def is_community_organization(org: dict[str, Any] | None) -> bool:
    if not org:
        return False
    return str(org.get("edition") or org.get("tier") or "").strip().lower() == COMMUNITY_EDITION


def billing_enabled(org: dict[str, Any] | None) -> bool:
    if is_community_organization(org):
        return False
    return bool((org or {}).get("billing_enabled", True))


def member_limit(org: dict[str, Any] | None) -> int | None:
    if is_community_organization(org):
        return None
    raw_limit = (org or {}).get("user_limit", 5)
    if raw_limit is None:
        return None
    return max(0, int(raw_limit))


def community_organization_fields(
    *, main_id: str, org_name: str, owner_user_id: str = "", total_points: int = 0
) -> dict[str, Any]:
    return {
        "main_id": main_id,
        "org_name": org_name or "MOVO 社区组织",
        "edition": COMMUNITY_EDITION,
        "tier": COMMUNITY_EDITION,
        "billing_enabled": False,
        "user_limit": None,
        "is_own_model": True,
        "owner_user_id": str(owner_user_id or ""),
        "total_points": max(0, int(total_points or 0)),
        "updated_at": datetime.now(timezone.utc),
    }


async def ensure_community_organization(
    *, main_id: str, org_name: str, owner_user_id: str = "", total_points: int = 0
) -> dict[str, Any]:
    db = get_db()
    now = datetime.now(timezone.utc)
    fields = community_organization_fields(
        main_id=main_id,
        org_name=org_name,
        owner_user_id=owner_user_id,
        total_points=total_points,
    )
    await db[ORGANIZATION_COLLECTION].update_one(
        {"main_id": main_id},
        {"$set": fields, "$setOnInsert": {"used_points": 0, "created_at": now}},
        upsert=True,
    )
    return await db[ORGANIZATION_COLLECTION].find_one({"main_id": main_id}) or fields


async def migrate_bootstrapped_community_organization() -> bool:
    """Mark only the tenant created by the self-hosted setup flow as community."""
    db = get_db()
    state = await db[SETUP_COLLECTION].find_one({"_id": "singleton", "completed": True})
    if not state:
        return False
    main_id = str(state.get("main_id") or "").strip()
    if not main_id:
        return False
    quota = await db[ORG_QUOTA_COLLECTION].find_one({"main_id": main_id}) or {}
    owner = await db[USER_COLLECTION].find_one({"main_id": main_id}, {"_id": 1}) or {}
    await ensure_community_organization(
        main_id=main_id,
        org_name=str(state.get("org_name") or "MOVO 社区组织"),
        owner_user_id=str(owner.get("_id") or ""),
        total_points=int(quota.get("total_tokens") or 0),
    )
    return True


async def assert_member_capacity(main_id: str) -> None:
    db = get_db()
    org = await db[ORGANIZATION_COLLECTION].find_one({"main_id": main_id})
    limit = member_limit(org)
    if limit is None:
        return
    current_count = await db[USER_COLLECTION].count_documents({"main_id": main_id})
    if current_count >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"当前版本最多允许 {limit} 名成员",
        )
