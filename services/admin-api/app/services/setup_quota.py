from __future__ import annotations

from app.core.db import get_db
from app.core.quota_policy import (
    ORG_QUOTA_POLICY_COLLECTION,
    USER_QUOTA_LOG_COLLECTION,
    USER_QUOTA_POLICY_COLLECTION,
    normalize_period,
    normalize_timezone,
    utc_now,
)


async def configure_setup_quotas(
    *,
    main_id: str,
    total_tokens: int,
    default_user_tokens: int,
    period: str,
    timezone_name: str,
    operator: str,
) -> None:
    if total_tokens <= 0:
        raise ValueError("企业总 Token 必须大于 0")
    if default_user_tokens <= 0:
        raise ValueError("员工默认 Token 必须大于 0")
    if default_user_tokens > total_tokens:
        raise ValueError("员工默认 Token 不能超过企业总 Token")

    db = get_db()
    now = utc_now()
    normalized_period = normalize_period(period)
    normalized_timezone = normalize_timezone(timezone_name)
    await db[ORG_QUOTA_POLICY_COLLECTION].update_one(
        {"main_id": main_id},
        {
            "$set": {
                "total_tokens": int(total_tokens),
                "period": normalized_period,
                "timezone": normalized_timezone,
                "status": "active",
                "updated_by": operator,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    await db[USER_QUOTA_POLICY_COLLECTION].update_one(
        {"main_id": main_id, "scope_type": "all", "scope_id": ""},
        {
            "$set": {
                "quota_tokens": int(default_user_tokens),
                "period": normalized_period,
                "priority": 10,
                "status": "active",
                "updated_by": operator,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    await db[USER_QUOTA_LOG_COLLECTION].insert_many(
        [
            {
                "main_id": main_id,
                "user_id": "org_policy",
                "action": "setup_org",
                "before_quota_tokens": 0,
                "after_quota_tokens": int(total_tokens),
                "delta_tokens": int(total_tokens),
                "reason": "初始化企业总额度",
                "operator": operator,
                "created_at": now,
            },
            {
                "main_id": main_id,
                "user_id": "default_policy",
                "action": "setup_default",
                "before_quota_tokens": 0,
                "after_quota_tokens": int(default_user_tokens),
                "delta_tokens": int(default_user_tokens),
                "reason": "初始化员工默认额度",
                "operator": operator,
                "created_at": now,
            },
        ]
    )
