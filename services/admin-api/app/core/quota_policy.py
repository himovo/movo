from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.core.db import get_db

ORG_COLLECTION = "organizations"
USER_COLLECTION = "end_users"
USER_ORG_REL_COLLECTION = "end_user_org_relations"
TOKEN_USAGE_COLLECTION = "token_usage_logs"
ORG_QUOTA_POLICY_COLLECTION = "org_quota_policies"
USER_QUOTA_POLICY_COLLECTION = "user_quota_policies"
USER_QUOTA_OVERRIDE_COLLECTION = "user_quota_overrides"
USER_QUOTA_LOG_COLLECTION = "user_token_allocation_logs"

VALID_PERIODS = {"monthly", "daily", "hourly"}
DEFAULT_TIMEZONE = "Asia/Shanghai"


class QuotaExceededError(ValueError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_period(value: Any) -> str:
    period = str(value or "monthly").strip().lower()
    return period if period in VALID_PERIODS else "monthly"


def normalize_timezone(value: Any) -> str:
    name = str(value or DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
    try:
        ZoneInfo(name)
        return name
    except Exception:
        return DEFAULT_TIMEZONE


def period_window(period: str, tz_name: str = DEFAULT_TIMEZONE, now: datetime | None = None) -> tuple[datetime, datetime]:
    zone = ZoneInfo(normalize_timezone(tz_name))
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    local_now = current.astimezone(zone)
    normalized_period = normalize_period(period)
    if normalized_period == "hourly":
        start_local = local_now.replace(minute=0, second=0, microsecond=0)
        end_local = start_local + timedelta(hours=1)
    elif normalized_period == "daily":
        start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = start_local + _one_day()
    else:
        start_local = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start_local.month == 12:
            end_local = start_local.replace(year=start_local.year + 1, month=1)
        else:
            end_local = start_local.replace(month=start_local.month + 1)
    return (
        start_local.astimezone(timezone.utc),
        end_local.astimezone(timezone.utc),
    )


def _one_day():
    from datetime import timedelta

    return timedelta(days=1)


async def ensure_org_quota_policy(main_id: str, *, org_total_points: int = 0) -> dict[str, Any]:
    db = get_db()
    policy = await db[ORG_QUOTA_POLICY_COLLECTION].find_one({"main_id": main_id})
    if policy:
        return policy
    now = utc_now()
    total = max(int(org_total_points or 0), 0)
    policy = {
        "main_id": main_id,
        "total_tokens": total,
        "period": "monthly",
        "timezone": DEFAULT_TIMEZONE,
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    await db[ORG_QUOTA_POLICY_COLLECTION].update_one({"main_id": main_id}, {"$setOnInsert": policy}, upsert=True)
    return await db[ORG_QUOTA_POLICY_COLLECTION].find_one({"main_id": main_id}) or policy


async def ensure_default_user_policy(main_id: str, *, period: str = "monthly") -> dict[str, Any]:
    db = get_db()
    query = {"main_id": main_id, "scope_type": "all", "scope_id": ""}
    policy = await db[USER_QUOTA_POLICY_COLLECTION].find_one(query)
    if policy:
        return policy
    now = utc_now()
    policy = {
        **query,
        "quota_tokens": 0,
        "period": normalize_period(period),
        "priority": 10,
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    await db[USER_QUOTA_POLICY_COLLECTION].update_one(query, {"$setOnInsert": policy}, upsert=True)
    return await db[USER_QUOTA_POLICY_COLLECTION].find_one(query) or policy


async def sum_usage(main_id: str, *, user_id: str = "", start_at: datetime, end_at: datetime) -> int:
    db = get_db()
    match: dict[str, Any] = {
        "main_id": main_id,
        "created_at": {"$gte": start_at, "$lt": end_at},
        "status": {"$ne": "failed"},
    }
    if user_id:
        match["user_id"] = user_id
    rows = await db[TOKEN_USAGE_COLLECTION].aggregate(
        [{"$match": match}, {"$group": {"_id": None, "tokens": {"$sum": {"$ifNull": ["$total_tokens", 0]}}}}],
    ).to_list(length=1)
    return int(rows[0].get("tokens") or 0) if rows else 0


async def resolve_user_policy(main_id: str, user_id: str) -> dict[str, Any]:
    db = get_db()
    user_policy = await db[USER_QUOTA_POLICY_COLLECTION].find_one(
        {"main_id": main_id, "scope_type": "user", "scope_id": user_id},
        sort=[("priority", -1), ("updated_at", -1)],
    )
    if user_policy:
        return user_policy
    org_policy = await db[ORG_QUOTA_POLICY_COLLECTION].find_one({"main_id": main_id})
    org_period = org_policy.get("period") if org_policy else "monthly"
    default_policy = await ensure_default_user_policy(main_id, period=org_period)
    return default_policy


async def sum_active_overrides(main_id: str, user_id: str, now: datetime | None = None) -> int:
    db = get_db()
    current = now or utc_now()
    rows = await db[USER_QUOTA_OVERRIDE_COLLECTION].aggregate(
        [
            {
                "$match": {
                    "main_id": main_id,
                    "user_id": user_id,
                    "status": "active",
                    "$or": [{"expires_at": {"$exists": False}}, {"expires_at": None}, {"expires_at": {"$gt": current}}],
                }
            },
            {"$group": {"_id": None, "tokens": {"$sum": {"$ifNull": ["extra_tokens", 0]}}}},
        ],
    ).to_list(length=1)
    return int(rows[0].get("tokens") or 0) if rows else 0


async def get_quota_summary(main_id: str, user: dict[str, Any]) -> dict[str, Any]:
    db = get_db()
    user_id = str(user.get("_id") or "")
    space_type = str(user.get("space_type") or "").strip().lower()
    if space_type not in {"personal", "enterprise"}:
        space_type = "personal" if str(user.get("org_name") or "").strip() == "个人空间" else "enterprise"
    org = await db[ORG_COLLECTION].find_one({"main_id": main_id}) or {}

    if space_type != "enterprise":
        total = int(org.get("total_points") or 0)
        used = int(org.get("used_points") or 0)
        return {
            "mainId": main_id,
            "orgName": org.get("org_name") or user.get("org_name") or "个人空间",
            "spaceType": "personal",
            "quotaSource": "registration_gift",
            "period": "lifetime",
            "totalPoints": total,
            "usedPoints": used,
            "remainingPoints": max(0, total - used),
            "resetAt": "",
            "status": "active",
        }

    org_policy = await ensure_org_quota_policy(main_id, org_total_points=int(org.get("total_points") or 0))
    user_policy = await resolve_user_policy(main_id, user_id)
    tz_name = normalize_timezone(org_policy.get("timezone"))
    org_start, org_end = period_window(str(org_policy.get("period") or "monthly"), tz_name)
    user_start, user_end = period_window(str(user_policy.get("period") or org_policy.get("period") or "monthly"), tz_name)
    org_used = await sum_usage(main_id, start_at=org_start, end_at=org_end)
    user_used = await sum_usage(main_id, user_id=user_id, start_at=user_start, end_at=user_end)
    org_total = int(org_policy.get("total_tokens") or 0)
    base_user_total = int(user_policy.get("quota_tokens") or 0)
    extra = await sum_active_overrides(main_id, user_id)
    user_total = max(0, base_user_total + extra)
    remaining = max(0, min(user_total - user_used, org_total - org_used))
    return {
        "mainId": main_id,
        "orgName": org.get("org_name") or user.get("org_name") or "组织空间",
        "spaceType": "enterprise",
        "quotaSource": "enterprise_allocation",
        "period": normalize_period(user_policy.get("period") or org_policy.get("period")),
        "totalPoints": user_total,
        "usedPoints": user_used,
        "remainingPoints": remaining,
        "resetAt": user_end.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "active" if org_policy.get("status") == "active" else "disabled",
        "orgTotalPoints": org_total,
        "orgUsedPoints": org_used,
        "orgRemainingPoints": max(0, org_total - org_used),
    }


async def assert_quota_available(main_id: str, user: dict[str, Any]) -> dict[str, Any]:
    summary = await get_quota_summary(main_id, user)
    if summary.get("status") != "active":
        raise QuotaExceededError("当前空间额度策略未启用，请联系管理员。")
    if int(summary.get("remainingPoints") or 0) <= 0:
        if summary.get("spaceType") == "enterprise":
            raise QuotaExceededError("当前企业分派额度已用尽，请联系企业管理员调整额度。")
        raise QuotaExceededError("个人赠送额度已用尽，请升级或切换到有可用额度的空间。")
    return summary
