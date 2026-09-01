from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Depends

from app.api.deps import get_current_admin_user
from app.core.db import get_db
from app.core.product_edition import billing_enabled, is_community_organization, member_limit
from app.repositories.directory_repository import DEPARTMENT_COLLECTION, USER_COLLECTION, USER_ORG_REL_COLLECTION
from app.repositories.model_repository import INSTANCE_COLLECTION

router = APIRouter()

SKILL_COLLECTION = "skills"
TOOL_COLLECTION = "external_tools"
ORG_COLLECTION = "organizations"
TOKEN_USAGE_COLLECTION = "token_usage_logs"

MODEL_PRICES = {
    "deepseek-v4-flash": (0.5, 1.5),
    "gpt-5.2-chat": (35.0, 110.0),
    "gpt-5.2": (35.0, 110.0),
    "gpt-5.4": (100.0, 300.0),
    "qwen3-vl-plus": (10.0, 10.0),
}
DEFAULT_PRICE = (10.0, 30.0)


def _fmt_time(value: Any) -> str | None:
    if not isinstance(value, datetime):
        return None
    normalized = value
    if normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=timezone.utc)
    return normalized.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _duration_ms(row: dict[str, Any]) -> int:
    start_time = int(row.get("start_time") or 0)
    end_time = int(row.get("end_time") or 0)
    return max(0, end_time - start_time) if start_time and end_time else 0


def _cost(model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
    in_price, out_price = MODEL_PRICES.get(str(model_name or "").strip(), DEFAULT_PRICE)
    return (prompt_tokens * in_price + completion_tokens * out_price) / 1_000_000.0


async def _billing(db: Any, main_id: str, current_user: dict[str, Any]) -> dict[str, Any]:
    org = await db[ORG_COLLECTION].find_one({"main_id": main_id})
    if not org:
        org = {
            "main_id": main_id,
            "org_name": current_user.get("org_name") or "组织空间",
            "tier": "free",
            "user_limit": 5,
            "total_points": 0,
            "used_points": 0,
            "is_own_model": False,
        }
    current_members = await db[USER_COLLECTION].count_documents({"main_id": main_id})
    total_points = int(org.get("total_points") or 0)
    used_points = int(org.get("used_points") or 0)
    return {
        "mainId": org.get("main_id") or main_id,
        "orgName": org.get("org_name") or current_user.get("org_name") or "组织空间",
        "edition": "community" if is_community_organization(org) else str(org.get("edition") or "cloud"),
        "tier": org.get("tier", "free"),
        "billingEnabled": billing_enabled(org),
        "userLimit": member_limit(org),
        "currentMembersCount": current_members,
        "totalPoints": total_points,
        "usedPoints": used_points,
        "remainingPoints": max(0, total_points - used_points),
        "isOwnModel": bool(org.get("is_own_model", False)),
    }


async def _usage_metrics(db: Any, main_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=1)
    match = {"main_id": main_id, "created_at": {"$gte": since}}
    usage_coll = db[TOKEN_USAGE_COLLECTION]

    rows = await usage_coll.aggregate(
        [
            {"$match": match},
            {
                "$group": {
                    "_id": "$model_name",
                    "calls": {"$sum": 1},
                    "failed_calls": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}},
                    "total_tokens": {"$sum": {"$ifNull": ["$total_tokens", 0]}},
                    "prompt_tokens": {"$sum": {"$ifNull": ["$prompt_tokens", 0]}},
                    "completion_tokens": {"$sum": {"$ifNull": ["$completion_tokens", 0]}},
                    "active_users": {"$addToSet": "$user_id"},
                    "last_called_at": {"$max": "$created_at"},
                    "duration_sum": {
                        "$sum": {
                            "$max": [
                                0,
                                {"$subtract": [{"$ifNull": ["$end_time", 0]}, {"$ifNull": ["$start_time", 0]}]},
                            ]
                        }
                    },
                    "timed_calls": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$and": [
                                        {"$gt": [{"$ifNull": ["$start_time", 0]}, 0]},
                                        {"$gt": [{"$ifNull": ["$end_time", 0]}, 0]},
                                    ]
                                },
                                1,
                                0,
                            ]
                        }
                    },
                }
            },
        ]
    ).to_list(length=1000)

    total_calls = 0
    failed_calls = 0
    total_tokens = 0
    total_cost = 0.0
    active_users: set[str] = set()
    last_called_at: datetime | None = None
    duration_sum = 0
    timed_calls = 0

    for row in rows:
        model_name = str(row.get("_id") or "")
        row_prompt = int(row.get("prompt_tokens") or 0)
        row_completion = int(row.get("completion_tokens") or 0)
        total_calls += int(row.get("calls") or 0)
        failed_calls += int(row.get("failed_calls") or 0)
        total_tokens += int(row.get("total_tokens") or 0)
        total_cost += _cost(model_name, row_prompt, row_completion)
        duration_sum += int(row.get("duration_sum") or 0)
        timed_calls += int(row.get("timed_calls") or 0)
        for user_id in row.get("active_users") or []:
            if user_id:
                active_users.add(str(user_id))
        row_last = row.get("last_called_at")
        if row_last and (last_called_at is None or row_last > last_called_at):
            last_called_at = row_last

    active_dept_count = 0
    if active_users:
        active_depts = await db[USER_ORG_REL_COLLECTION].distinct("org_id", {"main_id": main_id, "user_id": {"$in": list(active_users)}})
        active_dept_count = len([item for item in active_depts if str(item or "").strip()])

    recent_rows = (
        await usage_coll.find({"main_id": main_id})
        .sort([("created_at", -1), ("end_time", -1)])
        .limit(8)
        .to_list(length=8)
    )

    recent_activity = await _format_recent_activity(db, main_id, recent_rows)
    avg_duration = int(duration_sum / timed_calls) if timed_calls else 0
    return (
        {
            "calls24h": total_calls,
            "tokens24h": total_tokens,
            "cost24h": round(total_cost, 4),
            "activeUsers24h": len(active_users),
            "activeDepartments24h": active_dept_count,
            "failedCalls24h": failed_calls,
            "successRate24h": round(((total_calls - failed_calls) / total_calls) * 100, 2) if total_calls else None,
            "avgDurationMs24h": avg_duration,
            "lastCalledAt": _fmt_time(last_called_at),
        },
        recent_activity,
    )


async def _format_recent_activity(db: Any, main_id: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    user_ids = [str(row.get("user_id") or "") for row in rows if str(row.get("user_id") or "").strip()]
    user_oid_map = {user_id: ObjectId(user_id) for user_id in user_ids if ObjectId.is_valid(user_id)}
    user_docs = []
    if user_oid_map:
        user_docs = await db[USER_COLLECTION].find({"_id": {"$in": list(user_oid_map.values())}}).to_list(length=500)
    user_map = {str(doc.get("_id")): doc for doc in user_docs}

    rel_rows = await db[USER_ORG_REL_COLLECTION].find({"main_id": main_id, "user_id": {"$in": user_ids}}).to_list(length=1000) if user_ids else []
    rel_map: dict[str, str] = {}
    dept_ids = set[str]()
    for rel in rel_rows:
        user_id = str(rel.get("user_id") or "")
        org_id = str(rel.get("org_id") or "")
        if user_id and org_id and user_id not in rel_map:
            rel_map[user_id] = org_id
            dept_ids.add(org_id)

    dept_oid_map = {dept_id: ObjectId(dept_id) for dept_id in dept_ids if ObjectId.is_valid(dept_id)}
    dept_docs = []
    if dept_oid_map:
        dept_docs = await db[DEPARTMENT_COLLECTION].find({"_id": {"$in": list(dept_oid_map.values())}}, {"name": 1}).to_list(length=500)
    dept_map = {str(doc.get("_id")): str(doc.get("name") or "") for doc in dept_docs}

    items: list[dict[str, Any]] = []
    for row in rows:
        user_id = str(row.get("user_id") or "")
        user_doc = user_map.get(user_id, {})
        user_name = (
            str(user_doc.get("name") or "")
            or str(user_doc.get("login_name") or "")
            or str(user_doc.get("mobile") or "")
            or (f"用户 {user_id[-6:]}" if user_id else "未知用户")
        )
        dept_id = rel_map.get(user_id, "")
        title = str(row.get("request_title_zh") or row.get("request_title_en") or row.get("intent") or "LLM 调用")
        items.append(
            {
                "requestId": str(row.get("request_id") or ""),
                "sessionId": str(row.get("session_id") or ""),
                "userName": user_name,
                "departmentName": dept_map.get(dept_id, "未分配部门") if dept_id else "未分配部门",
                "modelName": str(row.get("model_name") or ""),
                "title": title,
                "status": str(row.get("status") or ""),
                "totalTokens": int(row.get("total_tokens") or 0),
                "durationMs": _duration_ms(row),
                "createdAt": _fmt_time(row.get("created_at")),
            }
        )
    return items


async def _assets(db: Any, main_id: str) -> dict[str, Any]:
    users_total = await db[USER_COLLECTION].count_documents({"main_id": main_id})
    users_disabled = await db[USER_COLLECTION].count_documents({"main_id": main_id, "status": "disabled"})
    departments_total = await db[DEPARTMENT_COLLECTION].count_documents({"main_id": main_id})

    model_rows = await db[INSTANCE_COLLECTION].find({"main_id": main_id}).to_list(length=1000)
    active_models = [row for row in model_rows if row.get("status") == "active"]
    failed_models = [row for row in model_rows if row.get("health_status") == "failed"]

    skill_rows = await db[SKILL_COLLECTION].find({"main_id": main_id}).to_list(length=2000)
    enabled_skills = [row for row in skill_rows if row.get("enabled", True)]
    workflow_skills = [row for row in skill_rows if row.get("type") == "workflow"]
    writing_skills = [row for row in skill_rows if row.get("type") == "writing_style"]

    tool_rows = await db[TOOL_COLLECTION].find({"main_id": main_id}).to_list(length=2000)
    active_tools = [row for row in tool_rows if row.get("status") == "active"]
    failed_tools = [row for row in tool_rows if row.get("last_test_status") == "failed"]
    untested_tools = [row for row in tool_rows if row.get("last_test_status") in (None, "", "untested")]
    mcp_tools = [row for row in tool_rows if row.get("type") == "mcp"]

    return {
        "users": {
            "total": users_total,
            "disabled": users_disabled,
            "departments": departments_total,
        },
        "models": {
            "total": len(model_rows),
            "active": len(active_models),
            "failedHealth": len(failed_models),
        },
        "skills": {
            "total": len(skill_rows),
            "enabled": len(enabled_skills),
            "workflow": len(workflow_skills),
            "writingStyle": len(writing_skills),
        },
        "tools": {
            "total": len(tool_rows),
            "active": len(active_tools),
            "mcp": len(mcp_tools),
            "failed": len(failed_tools),
            "untested": len(untested_tools),
        },
    }


def _todos(metrics: dict[str, Any], assets: dict[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    models = assets["models"]
    skills = assets["skills"]
    tools = assets["tools"]

    if models["total"] == 0:
        items.append({"level": "warning", "title": "尚未配置模型", "description": "添加模型后前台用户才能稳定调用 LLM。", "route": "/models"})
    if models["failedHealth"] > 0:
        items.append({"level": "error", "title": "存在模型健康异常", "description": f"{models['failedHealth']} 个模型最近测试失败。", "route": "/models"})
    if tools["failed"] > 0:
        items.append({"level": "error", "title": "工具测试失败", "description": f"{tools['failed']} 个工具连接需要检查。", "route": "/tools"})
    if tools["untested"] > 0:
        items.append({"level": "info", "title": "工具未完成测试", "description": f"{tools['untested']} 个工具尚未测试连通性。", "route": "/tools"})
    if skills["total"] > 0 and skills["enabled"] == 0:
        items.append({"level": "warning", "title": "Skill 均未启用", "description": "启用至少一个 Skill 后可在前台使用。", "route": "/skills"})
    if metrics["failedCalls24h"] > 0:
        items.append({"level": "warning", "title": "近 24 小时有失败调用", "description": f"{metrics['failedCalls24h']} 次调用失败，建议查看 Token 统计。", "route": "/token-stats"})
    return items[:6]


@router.get("/overview")
async def overview(current_user: dict = Depends(get_current_admin_user)) -> dict[str, Any]:
    main_id = str(current_user.get("main_id") or "default")
    db = get_db()
    billing = await _billing(db, main_id, current_user)
    metrics, recent_activity = await _usage_metrics(db, main_id)
    assets = await _assets(db, main_id)
    todos = _todos(metrics, assets)
    status_text = "critical" if any(item["level"] == "error" for item in todos) else "warning" if todos else "healthy"
    return {
        "billing": billing,
        "health": {
            "status": status_text,
            "warnings": [item["title"] for item in todos],
        },
        "metrics": metrics,
        "assets": assets,
        "todos": todos,
        "recentActivity": recent_activity,
    }
