from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import get_current_admin_user
from app.core.db import get_db
from app.core.quota_policy import (
    ORG_COLLECTION,
    ORG_QUOTA_POLICY_COLLECTION,
    USER_COLLECTION,
    USER_ORG_REL_COLLECTION,
    USER_QUOTA_LOG_COLLECTION,
    USER_QUOTA_POLICY_COLLECTION,
    ensure_default_user_policy,
    ensure_org_quota_policy,
    get_quota_summary,
    normalize_period,
    normalize_timezone,
    period_window,
    sum_usage,
    utc_now,
)
from app.repositories.directory_repository import DEPARTMENT_COLLECTION

router = APIRouter()


class OrgQuotaPayload(BaseModel):
    totalTokens: int = Field(default=0, ge=0)
    period: str = Field(default="monthly")
    timezone: str = Field(default="Asia/Shanghai")
    status: str = Field(default="active", pattern=r"^(active|disabled)$")


class DefaultPolicyPayload(BaseModel):
    quotaTokens: int = Field(default=0, ge=0)
    period: str = Field(default="monthly")
    status: str = Field(default="active", pattern=r"^(active|disabled)$")


class UserPolicyPayload(BaseModel):
    userId: str = Field(min_length=1)
    quotaTokens: int = Field(default=0, ge=0)
    period: str = Field(default="monthly")
    reason: str = Field(default="", max_length=200)


def _main_id(current_user: dict[str, Any]) -> str:
    return str(current_user.get("main_id") or "default")


def _fmt(value: Any) -> str:
    if not isinstance(value, datetime):
        return ""
    normalized = value
    if normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=timezone.utc)
    return normalized.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


async def _department_maps(main_id: str) -> tuple[dict[str, str], dict[str, str]]:
    db = get_db()
    deps = await db[DEPARTMENT_COLLECTION].find({"main_id": main_id}).to_list(length=10000)
    dep_names = {str(item.get("_id")): str(item.get("name") or "") for item in deps}
    rels = await db[USER_ORG_REL_COLLECTION].find({"main_id": main_id}).to_list(length=50000)
    primary: dict[str, str] = {}
    for rel in rels:
        user_id = str(rel.get("user_id") or "")
        if rel.get("is_primary") and user_id:
            primary[user_id] = str(rel.get("org_id") or "")
    return dep_names, primary


@router.get("/overview")
async def get_traffic_allocation_overview(current_user: dict[str, Any] = Depends(get_current_admin_user)) -> dict[str, Any]:
    main_id = _main_id(current_user)
    db = get_db()
    org = await db[ORG_COLLECTION].find_one({"main_id": main_id}) or {}
    org_policy = await ensure_org_quota_policy(main_id, org_total_points=int(org.get("total_points") or 0))
    default_policy = await ensure_default_user_policy(main_id, period=str(org_policy.get("period") or "monthly"))
    tz_name = normalize_timezone(org_policy.get("timezone"))
    start_at, end_at = period_window(str(org_policy.get("period") or "monthly"), tz_name)
    org_used = await sum_usage(main_id, start_at=start_at, end_at=end_at)
    assigned_policies = await db[USER_QUOTA_POLICY_COLLECTION].find(
        {"main_id": main_id, "scope_type": "user"},
        {"scope_id": 1, "quota_tokens": 1},
    ).to_list(length=50000)
    policy_user_ids = [str(policy.get("scope_id") or "") for policy in assigned_policies]
    valid_user_oids = [ObjectId(user_id) for user_id in policy_user_ids if ObjectId.is_valid(user_id)]
    existing_user_rows = (
        await db[USER_COLLECTION].find({"_id": {"$in": valid_user_oids}, "main_id": main_id}, {"_id": 1}).to_list(length=len(valid_user_oids))
        if valid_user_oids
        else []
    )
    existing_user_ids = {str(user.get("_id")) for user in existing_user_rows}
    assigned_count = 0
    assigned_tokens = 0
    for policy in assigned_policies:
        if str(policy.get("scope_id") or "") not in existing_user_ids:
            continue
        assigned_count += 1
        assigned_tokens += int(policy.get("quota_tokens") or 0)
    total = int(org_policy.get("total_tokens") or 0)
    return {
        "orgPolicy": {
            "totalTokens": total,
            "period": normalize_period(org_policy.get("period")),
            "timezone": tz_name,
            "status": org_policy.get("status") or "active",
            "usedTokens": org_used,
            "remainingTokens": max(0, total - org_used),
            "periodStartAt": _fmt(start_at),
            "resetAt": _fmt(end_at),
        },
        "defaultPolicy": {
            "quotaTokens": int(default_policy.get("quota_tokens") or 0),
            "period": normalize_period(default_policy.get("period")),
            "status": default_policy.get("status") or "active",
        },
        "assignedTokens": assigned_tokens,
        "assignedPolicyCount": assigned_count,
    }


@router.put("/org-policy")
async def update_org_quota_policy(payload: OrgQuotaPayload, current_user: dict[str, Any] = Depends(get_current_admin_user)) -> dict[str, bool]:
    main_id = _main_id(current_user)
    now = utc_now()
    db = get_db()
    existing = await db[ORG_QUOTA_POLICY_COLLECTION].find_one({"main_id": main_id})
    before = int((existing or {}).get("total_tokens") or 0)
    await db[ORG_QUOTA_POLICY_COLLECTION].update_one(
        {"main_id": main_id},
        {
            "$set": {
                "total_tokens": int(payload.totalTokens),
                "period": normalize_period(payload.period),
                "timezone": normalize_timezone(payload.timezone),
                "status": payload.status,
                "updated_by": str(current_user.get("username") or ""),
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    await db[USER_QUOTA_LOG_COLLECTION].insert_one(
        {
            "main_id": main_id,
            "user_id": "org_policy",
            "action": "set_org",
            "before_quota_tokens": before,
            "after_quota_tokens": int(payload.totalTokens),
            "delta_tokens": int(payload.totalTokens) - before,
            "reason": "修改企业本周期总额度",
            "operator": str(current_user.get("username") or ""),
            "created_at": now,
        }
    )
    return {"success": True}



@router.put("/default-policy")
async def update_default_user_policy(payload: DefaultPolicyPayload, current_user: dict[str, Any] = Depends(get_current_admin_user)) -> dict[str, bool]:
    main_id = _main_id(current_user)
    now = utc_now()
    db = get_db()
    
    org_policy = await ensure_org_quota_policy(main_id)
    if int(org_policy.get("total_tokens") or 0) == 0 and int(payload.quotaTokens) > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前企业本周期总额度为 0，不能为成员分配大于 0 的额度。请先配置企业总额度。"
        )

    existing = await db[USER_QUOTA_POLICY_COLLECTION].find_one({"main_id": main_id, "scope_type": "all", "scope_id": ""})

    before = int((existing or {}).get("quota_tokens") or 0)
    await db[USER_QUOTA_POLICY_COLLECTION].update_one(
        {"main_id": main_id, "scope_type": "all", "scope_id": ""},
        {
            "$set": {
                "quota_tokens": int(payload.quotaTokens),
                "period": normalize_period(payload.period),
                "priority": 10,
                "status": payload.status,
                "updated_by": str(current_user.get("username") or ""),
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    # 级联更新该组织下所有专属用户的重置周期，以确保全局重置周期设置对所有专属用户也生效
    await db[USER_QUOTA_POLICY_COLLECTION].update_many(
        {"main_id": main_id, "scope_type": "user"},
        {
            "$set": {
                "period": normalize_period(payload.period),
                "updated_at": now,
            }
        }
    )
    await db[USER_QUOTA_LOG_COLLECTION].insert_one(
        {
            "main_id": main_id,
            "user_id": "default_policy",
            "action": "set_default",
            "before_quota_tokens": before,
            "after_quota_tokens": int(payload.quotaTokens),
            "delta_tokens": int(payload.quotaTokens) - before,
            "reason": "修改成员默认额度",
            "operator": str(current_user.get("username") or ""),
            "created_at": now,
        }
    )
    return {"success": True}




@router.get("/users")
async def list_user_allocations(
    current_user: dict[str, Any] = Depends(get_current_admin_user),
    keyword: str = Query(default=""),
    statusFilter: str = Query(default=""),
) -> list[dict[str, Any]]:
    main_id = _main_id(current_user)
    db = get_db()
    query: dict[str, Any] = {"main_id": main_id}
    if statusFilter:
        query["status"] = statusFilter
    if keyword.strip():
        regex = {"$regex": keyword.strip(), "$options": "i"}
        query["$or"] = [{"name": regex}, {"mobile": regex}, {"phone": regex}, {"email": regex}, {"login_name": regex}]
    users = await db[USER_COLLECTION].find(query).sort("updated_at", -1).to_list(length=5000)
    dep_names, primary_map = await _department_maps(main_id)
    rows: list[dict[str, Any]] = []
    for user in users:
        summary = await get_quota_summary(main_id, user)
        user_id = str(user.get("_id") or "")
        dep_id = primary_map.get(user_id, str(user.get("primary_org_id") or ""))
        rows.append(
            {
                "userId": user_id,
                "name": user.get("name") or user.get("login_name") or "",
                "loginName": user.get("login_name") or "",
                "email": user.get("email") or "",
                "mobile": user.get("mobile") or user.get("phone") or "",
                "status": user.get("status") or "active",
                "departmentName": dep_names.get(dep_id, ""),
                "quotaTokens": int(summary.get("totalPoints") or 0),
                "usedTokens": int(summary.get("usedPoints") or 0),
                "remainingTokens": int(summary.get("remainingPoints") or 0),
                "period": summary.get("period") or "monthly",
                "resetAt": summary.get("resetAt") or "",
            }
        )
    return rows


@router.put("/users/{user_id}/policy")
async def update_user_policy(
    user_id: str,
    payload: UserPolicyPayload,
    current_user: dict[str, Any] = Depends(get_current_admin_user),
) -> dict[str, bool]:
    main_id = _main_id(current_user)
    if payload.userId != user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户ID不一致")
    db = get_db()
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户ID无效")
    user = await db[USER_COLLECTION].find_one({"_id": ObjectId(user_id), "main_id": main_id})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
        
    org_policy = await ensure_org_quota_policy(main_id)
    if int(org_policy.get("total_tokens") or 0) == 0 and int(payload.quotaTokens) > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前企业本周期总额度为 0，不能为用户分配大于 0 的额度。请先配置企业总额度。"
        )

    query = {"main_id": main_id, "scope_type": "user", "scope_id": user_id}
    existing = await db[USER_QUOTA_POLICY_COLLECTION].find_one(query)

    before = int((existing or {}).get("quota_tokens") or 0)
    now = utc_now()
    await db[USER_QUOTA_POLICY_COLLECTION].update_one(
        query,
        {
            "$set": {
                "quota_tokens": int(payload.quotaTokens),
                "period": normalize_period(payload.period),
                "priority": 100,
                "status": "active",
                "updated_by": str(current_user.get("username") or ""),
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    await db[USER_QUOTA_LOG_COLLECTION].insert_one(
        {
            "main_id": main_id,
            "user_id": user_id,
            "action": "set",
            "before_quota_tokens": before,
            "after_quota_tokens": int(payload.quotaTokens),
            "delta_tokens": int(payload.quotaTokens) - before,
            "reason": payload.reason.strip(),
            "operator": str(current_user.get("username") or ""),
            "created_at": now,
        }
    )
    return {"success": True}


@router.get("/logs")
async def list_allocation_logs(
    current_user: dict[str, Any] = Depends(get_current_admin_user),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    main_id = _main_id(current_user)
    db = get_db()
    query = {"main_id": main_id}
    skip = (page - 1) * pageSize
    total = await db[USER_QUOTA_LOG_COLLECTION].count_documents(query)
    logs = await db[USER_QUOTA_LOG_COLLECTION].find(query).sort("created_at", -1).skip(skip).limit(pageSize).to_list(length=pageSize)
    user_ids = [ObjectId(row["user_id"]) for row in logs if ObjectId.is_valid(str(row.get("user_id") or ""))]
    users = await db[USER_COLLECTION].find({"_id": {"$in": user_ids}}).to_list(length=pageSize) if user_ids else []
    user_map = {str(user.get("_id")): user for user in users}
    return {
        "page": page,
        "pageSize": pageSize,
        "total": total,
        "items": [
            {
                "id": str(row.get("_id")),
                "userId": str(row.get("user_id") or ""),
                "userName": "新成员默认额度" if row.get("user_id") == "default_policy" else "企业本周期总额度" if row.get("user_id") == "org_policy" else user_map.get(str(row.get("user_id") or ""), {}).get("name") or "",
                "action": row.get("action") or "set",
                "beforeQuotaTokens": int(row.get("before_quota_tokens") or 0),
                "afterQuotaTokens": int(row.get("after_quota_tokens") or 0),
                "deltaTokens": int(row.get("delta_tokens") or 0),
                "reason": row.get("reason") or "",
                "operator": row.get("operator") or "",
                "createdAt": _fmt(row.get("created_at")),
            }
            for row in logs
        ],
    }
