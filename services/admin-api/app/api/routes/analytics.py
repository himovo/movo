from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_admin_user
from app.core.db import get_db
from app.repositories.directory_repository import DEPARTMENT_COLLECTION, USER_COLLECTION, USER_ORG_REL_COLLECTION
from app.services.token_usage_analytics_helpers import (
    extract_user_question_from_prompt,
    load_execution_statuses,
    load_user_request_texts,
)
from app.services.token_usage_status import REQUEST_STATUS_VALUES, normalize_request_status

router = APIRouter()


def _escape_regex(text: str) -> dict[str, str]:
    return {"$regex": re.escape(text), "$options": "i"}


def _resolve_main_scope(current_user: dict[str, Any], requested_main_id: str) -> tuple[dict[str, Any], str]:
    own_main_id = str(current_user.get("main_id") or "default")
    request_main_id = str(requested_main_id or "").strip()

    # Token 统计固定按当前登录企业隔离，禁止跨企业读取。
    if request_main_id and request_main_id != own_main_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权限查看其他企业数据")

    return {"main_id": own_main_id}, own_main_id


def _summary_defaults() -> dict[str, Any]:
    return {
        "totalCalls": 0,
        "totalTokens": 0,
        "promptTokens": 0,
        "completionTokens": 0,
        "avgTokens": 0,
        "lastCalledAt": None,
        "last24hCalls": 0,
        "last24hTokens": 0,
        "activeUsers": 0,
        "activeDepartments": 0,
    }


def _normalize_utc_datetime(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _format_utc_datetime(value: Any) -> str | None:
    normalized = _normalize_utc_datetime(value)
    if normalized is None:
        return None
    return normalized.isoformat().replace("+00:00", "Z")


@router.get("/token-usage")
async def list_token_usage(
    current_user: dict[str, Any] = Depends(get_current_admin_user),
    mainId: str = Query(default=""),
    departmentId: str = Query(default=""),
    modelName: str = Query(default=""),
    stage: str = Query(default=""),
    statusText: str = Query(default="", alias="status"),
    q: str = Query(default=""),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=200),
    groupBy: str = Query(default="user_request"),
    sessionId: str = Query(default=""),
    userRequestId: str = Query(default=""),
) -> dict[str, Any]:
    db = get_db()
    usage_coll = db.token_usage_logs
    user_coll = db[USER_COLLECTION]
    user_org_rel_coll = db[USER_ORG_REL_COLLECTION]
    dept_coll = db[DEPARTMENT_COLLECTION]

    scope_match, resolved_main_id = _resolve_main_scope(current_user, mainId)

    match: dict[str, Any] = dict(scope_match)
    if modelName.strip():
        match["model_name"] = modelName.strip()
    if stage.strip():
        match["stage"] = stage.strip()
    requested_status = statusText.strip()

    session_id_val = sessionId.strip()
    if session_id_val:
        match["session_id"] = session_id_val
    user_request_id_val = userRequestId.strip()
    if user_request_id_val:
        match["user_request_id"] = user_request_id_val

    department_id = departmentId.strip()
    if department_id:
        rel_match: dict[str, Any] = {"org_id": department_id}
        if resolved_main_id:
            rel_match["main_id"] = resolved_main_id
        elif scope_match.get("main_id"):
            rel_match["main_id"] = scope_match["main_id"]

        rel_rows = await user_org_rel_coll.find(rel_match, {"user_id": 1}).to_list(length=50000)
        allowed_user_ids = [str(row.get("user_id") or "") for row in rel_rows if str(row.get("user_id") or "").strip()]
        if not allowed_user_ids:
            return {
                "summary": _summary_defaults(),
                "items": [],
                "offset": offset,
                "limit": limit,
                "total": 0,
                "hasMore": False,
                "filterOptions": {
                    "enterprises": [],
                    "departments": [],
                    "models": [],
                    "stages": [],
                    "statuses": [],
                },
            }
        match["user_id"] = {"$in": allowed_user_ids}

    keyword = q.strip()
    if keyword:
        regex = _escape_regex(keyword)
        match = {
            "$and": [
                match,
                {
                    "$or": [
                        {"prompt": regex},
                        {"model_name": regex},
                        {"stage": regex},
                        {"status": regex},
                        {"request_title_zh": regex},
                        {"request_title_en": regex},
                        {"user_request_id": regex},
                        {"trace_id": regex},
                    ]
                },
            ]
        }

    if groupBy in {"user_request", "session"}:
        group_id_expr = {
            "$cond": {
                "if": {"$or": [{"$eq": ["$user_request_id", ""]}, {"$not": ["$user_request_id"]}]},
                "then": "$request_id",
                "else": "$user_request_id"
            }
        }
        # 1. 统计分组后的总条数
        count_pipeline = [
            {"$match": match},
            {"$group": {"_id": group_id_expr}},
            {"$count": "count"}
        ]
        count_res = await usage_coll.aggregate(count_pipeline).to_list(length=1)
        total = count_res[0]["count"] if count_res else 0

        # 2. 查询分页数据
        data_pipeline = [
            {"$match": match},
            {"$sort": {"created_at": 1}},
            {"$group": {
                "_id": group_id_expr,
                "session_id": {"$first": "$session_id"},
                "user_request_id": {"$first": "$user_request_id"},
                "trace_id": {"$first": "$trace_id"},
                "request_id": {"$first": "$request_id"},
                "main_id": {"$first": "$main_id"},
                "user_id": {"$first": "$user_id"},
                "stage": {"$first": "$stage"},
                "intent": {"$first": "$intent"},
                "node_id": {"$first": "$node_id"},
                "failed_count": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}},
                "error_text": {"$first": {"$ifNull": ["$response_payload.error", "$push_error"]}},
                "model_name": {"$first": "$model_name"},
                "request_title_zh": {"$first": "$request_title_zh"},
                "request_title_en": {"$first": "$request_title_en"},
                "prompt": {"$first": "$prompt"},
                "start_time": {"$min": "$start_time"},
                "end_time": {"$max": "$end_time"},
                "total_tokens": {"$sum": {"$ifNull": ["$total_tokens", 0]}},
                "prompt_tokens": {"$sum": {"$ifNull": ["$prompt_tokens", 0]}},
                "completion_tokens": {"$sum": {"$ifNull": ["$completion_tokens", 0]}},
                "created_at": {"$min": "$created_at"},
                "updated_at": {"$max": "$updated_at"},
                "calls": {"$sum": 1}
            }},
            {"$sort": {"created_at": -1}},
        ]
        rows = await usage_coll.aggregate(data_pipeline).to_list(length=50000)
        execution_statuses = await load_execution_statuses(rows, resolved_main_id)
        for row in rows:
            group_key = str(row.get("_id") or "").strip()
            row["status"] = normalize_request_status(
                execution_status=execution_statuses.get(group_key, ""),
                failed_count=row.get("failed_count"),
                error_text=row.get("error_text"),
            )
        if requested_status in REQUEST_STATUS_VALUES:
            rows = [row for row in rows if str(row.get("status") or "") == requested_status]
        filtered_rows = rows
        total = len(filtered_rows)
        rows = filtered_rows[offset : offset + limit]
    else:
        total = int(await usage_coll.count_documents(match))
        cursor = (
            usage_coll.find(match)
            .sort([("end_time", -1), ("created_at", -1)])
            .skip(offset)
            .limit(limit)
        )
        rows = await cursor.to_list(length=limit)
        for row in rows:
            row["calls"] = 1
        filtered_rows = rows

    user_ids = list({str(row.get("user_id") or "").strip() for row in rows if str(row.get("user_id") or "").strip()})
    user_oid_map = {uid: ObjectId(uid) for uid in user_ids if ObjectId.is_valid(uid)}
    user_docs = []
    if user_oid_map:
        user_docs = await user_coll.find({"_id": {"$in": list(user_oid_map.values())}}).to_list(length=20000)
    user_map: dict[str, dict[str, Any]] = {str(doc.get("_id")): doc for doc in user_docs}

    rel_rows = await user_org_rel_coll.find({"user_id": {"$in": user_ids}}).to_list(length=50000) if user_ids else []
    rel_map: dict[tuple[str, str], str] = {}
    dept_ids = set[str]()
    for rel in rel_rows:
        rel_user_id = str(rel.get("user_id") or "")
        rel_main_id = str(rel.get("main_id") or "")
        rel_org_id = str(rel.get("org_id") or "")
        if not rel_user_id or not rel_org_id:
            continue
        dept_ids.add(rel_org_id)
        key = (rel_user_id, rel_main_id)
        if key not in rel_map:
            rel_map[key] = rel_org_id

    dept_oid_map = {dept_id: ObjectId(dept_id) for dept_id in dept_ids if ObjectId.is_valid(dept_id)}
    dept_docs = []
    if dept_oid_map:
        dept_docs = await dept_coll.find({"_id": {"$in": list(dept_oid_map.values())}}, {"name": 1}).to_list(length=50000)
    dept_map = {str(doc.get("_id")): str(doc.get("name") or "") for doc in dept_docs}

    request_texts = await load_user_request_texts(rows, resolved_main_id)

    items: list[dict[str, Any]] = []
    for row in rows:
        row_user_id = str(row.get("user_id") or "")
        row_main_id = str(row.get("main_id") or "")
        user_doc = user_map.get(row_user_id, {})
        user_name = (
            str(user_doc.get("name") or "")
            or str(user_doc.get("login_name") or "")
            or str(user_doc.get("mobile") or "")
            or f"用户 {row_user_id[-6:]}" if row_user_id else "未知用户"
        )
        dept_id = rel_map.get((row_user_id, row_main_id), "")
        dept_name = dept_map.get(dept_id, "未分配部门") if dept_id else "未分配部门"
        created_at = row.get("created_at")
        start_time = int(row.get("start_time") or 0)
        end_time = int(row.get("end_time") or 0)
        duration_ms = max(0, end_time - start_time) if start_time and end_time else 0
        title_zh = str(row.get("request_title_zh") or "").strip()
        title_en = str(row.get("request_title_en") or "").strip()
        intent = str(row.get("intent") or "").strip()
        prompt_text = str(row.get("prompt") or "").strip()
        user_request_id = str(row.get("user_request_id") or "").strip()
        request_text = request_texts.get(user_request_id, "")
        title = request_text
        if not title and intent == "knowledge_qa":
            title = extract_user_question_from_prompt(prompt_text)
        if not title:
            title = title_zh or title_en or intent or "LLM 调用"
            if (title in ("意图路由", "LLM 调用", "LLM_Call", "Knowledge Qa", "Knowledge QA") or not title) and prompt_text:
                title = extract_user_question_from_prompt(prompt_text)
        prompt_preview = request_text or extract_user_question_from_prompt(prompt_text)
        items.append(
            {
                "requestId": str(row.get("request_id") or ""),
                "userRequestId": user_request_id,
                "mainId": row_main_id,
                "mainName": row_main_id or "默认企业",
                "userName": user_name,
                "departmentName": dept_name,
                "modelName": str(row.get("model_name") or ""),
                "stage": str(row.get("stage") or ""),
                "status": str(row.get("status") or ""),
                "requestTitle": title,
                "promptPreview": prompt_preview,
                "totalTokens": int(row.get("total_tokens") or 0),
                "promptTokens": int(row.get("prompt_tokens") or 0),
                "completionTokens": int(row.get("completion_tokens") or 0),
                "createdAt": _format_utc_datetime(created_at),
                "durationMs": duration_ms,
                "calls": int(row.get("calls") or 1),
                "sessionId": str(row.get("session_id") or ""),
            }
        )

    MODEL_PRICES = {
        "deepseek-v4-flash": (0.5, 1.5),
        "gpt-5.2-chat": (35.0, 110.0),
        "gpt-5.2": (35.0, 110.0),
        "gpt-5.4": (100.0, 300.0),
        "qwen3-vl-plus": (10.0, 10.0),
    }
    DEFAULT_PRICE = (10.0, 30.0)

    total_calls = 0
    total_tokens = 0
    prompt_tokens = 0
    completion_tokens = 0
    total_cost = 0.0
    last_called_at = None
    all_active_users = set()
    all_active_user_requests = set()
    recent_calls = 0
    recent_tokens = 0
    recent_cost = 0.0
    now = datetime.now(timezone.utc)
    recent_threshold = now - timedelta(days=1)

    for row in filtered_rows:
        model_name = str(row.get("model_name") or "").strip()
        in_price, out_price = MODEL_PRICES.get(model_name, DEFAULT_PRICE)
        row_prompt = int(row.get("prompt_tokens") or 0)
        row_comp = int(row.get("completion_tokens") or 0)
        row_cost = (row_prompt * in_price + row_comp * out_price) / 1000000.0
        row_total = int(row.get("total_tokens") or 0)
        row_calls = int(row.get("calls") or 1)

        total_calls += row_calls
        total_tokens += row_total
        prompt_tokens += row_prompt
        completion_tokens += row_comp
        total_cost += row_cost

        row_last = _normalize_utc_datetime(row.get("created_at"))
        if row_last:
            if last_called_at is None or row_last > last_called_at:
                last_called_at = row_last

        row_user_id = str(row.get("user_id") or "").strip()
        if row_user_id:
            all_active_users.add(row_user_id)
        row_request_id = str(row.get("user_request_id") or row.get("_id") or row.get("request_id") or "").strip()
        if row_request_id:
            all_active_user_requests.add(row_request_id)
        if isinstance(row_last, datetime) and row_last >= recent_threshold:
            recent_calls += row_calls
            recent_tokens += row_total
            recent_cost += row_cost

    active_user_ids = list(all_active_users)
    active_dept_count = 0
    if active_user_ids:
        dept_match: dict[str, Any] = {"user_id": {"$in": active_user_ids}}
        if resolved_main_id:
            dept_match["main_id"] = resolved_main_id
        distinct_depts = await user_org_rel_coll.distinct("org_id", dept_match)
        active_dept_count = len([dept_id for dept_id in distinct_depts if str(dept_id or "").strip()])

    request_count = len(all_active_user_requests)
    avg_tokens = 0.0
    avg_cost = 0.0
    if request_count > 0:
        avg_tokens = float(total_tokens) / request_count
        avg_cost = total_cost / request_count

    summary = {
        "totalCalls": total_calls,
        "totalTokens": total_tokens,
        "promptTokens": prompt_tokens,
        "completionTokens": completion_tokens,
        "avgTokens": round(avg_tokens, 1),
        "lastCalledAt": _format_utc_datetime(last_called_at),
        "last24hCalls": recent_calls,
        "last24hTokens": recent_tokens,
        "activeUsers": len(active_user_ids),
        "activeDepartments": int(active_dept_count),
        "totalCost": round(total_cost, 4),
        "avgCost": round(avg_cost, 4),
        "last24hCost": round(recent_cost, 4),
    }

    enterprise_scope_match = dict(scope_match)
    enterprises = sorted([str(item or "") for item in await usage_coll.distinct("main_id", enterprise_scope_match) if str(item or "").strip()])
    model_scope_match = dict(scope_match)
    if resolved_main_id:
        model_scope_match["main_id"] = resolved_main_id
    models = sorted([str(item or "") for item in await usage_coll.distinct("model_name", model_scope_match) if str(item or "").strip()])[:200]
    statuses = ["completed", "user_cancelled", "runtime_error", "network_error"]

    department_options: list[dict[str, str]] = []
    if resolved_main_id:
        dept_cursor = dept_coll.find({"main_id": resolved_main_id}, {"name": 1}).sort("created_at", 1)
        dept_rows = await dept_cursor.to_list(length=5000)
        department_options = [{"label": str(row.get("name") or ""), "value": str(row.get("_id"))} for row in dept_rows if str(row.get("name") or "").strip()]

    return {
        "summary": summary,
        "items": items,
        "offset": offset,
        "limit": limit,
        "total": total,
        "hasMore": offset + len(items) < total,
        "filterOptions": {
            "enterprises": [{"label": item, "value": item} for item in enterprises],
            "departments": department_options,
            "models": [{"label": item, "value": item} for item in models],
            "stages": [],
            "statuses": [{"label": item, "value": item} for item in statuses],
        },
    }


@router.get("/token-usage/{request_id}")
async def get_token_usage_detail(
    request_id: str,
    current_user: dict[str, Any] = Depends(get_current_admin_user),
) -> dict[str, Any]:
    db = get_db()
    usage_coll = db.token_usage_logs

    own_main_id = str(current_user.get("main_id") or "default")

    row = await usage_coll.find_one({"request_id": request_id})
    if not row:
        raise HTTPException(status_code=404, detail="未找到对应的调用记录")

    if str(row.get("main_id") or "default") != own_main_id:
        raise HTTPException(status_code=403, detail="无权查看该记录")

    return {
        "requestId": str(row.get("request_id") or ""),
        "prompt": str(row.get("prompt") or ""),
        "requestPayload": row.get("request_payload") or {},
        "responsePayload": row.get("response_payload") or {},
    }


@router.get("/token-usage/{request_id}/chat-history")
async def get_session_chat_history(
    request_id: str,
    sessionId: str = Query(default=""),
    userRequestId: str = Query(default=""),
    current_user: dict[str, Any] = Depends(get_current_admin_user),
) -> dict[str, Any]:
    db = get_db()
    own_main_id = str(current_user.get("main_id") or "default")
    
    # 1. 优先按一次用户请求定位当前 assistant 消息，并补上它前一条 user 消息。
    session_id_val = sessionId.strip()
    user_request_id_val = userRequestId.strip()
    messages = []
    session_title = ""

    def _message_payload(msg: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(msg.get("_id")),
            "role": str(msg.get("role") or ""),
            "content": str(msg.get("content") or ""),
            "plan": msg.get("plan") or None,
            "progress": msg.get("progress") or None,
            "documents": msg.get("documents") or [],
            "images": msg.get("images") or [],
            "createdAt": _format_utc_datetime(msg.get("created_at")),
        }

    if user_request_id_val:
        assistant_msg = await db.chat_messages.find_one(
            {
                "main_id": own_main_id,
                "message_id": user_request_id_val,
                "message_type": {"$ne": "context_summary"},
            }
        )
        if assistant_msg:
            session_oid = assistant_msg.get("session_id")
            session_doc = await db.chat_sessions.find_one({"_id": session_oid, "main_id": own_main_id}) if session_oid else None
            session_title = str(session_doc.get("title") or "单次请求详情") if session_doc else "单次请求详情"
            prev_user_msg = await db.chat_messages.find_one(
                {
                    "main_id": own_main_id,
                    "session_id": session_oid,
                    "role": "user",
                    "message_type": {"$ne": "context_summary"},
                    "seq": {"$lt": int(assistant_msg.get("seq") or 0)},
                },
                sort=[("seq", -1)],
            ) if session_oid else None
            if prev_user_msg:
                messages.append(_message_payload(prev_user_msg))
            messages.append(_message_payload(assistant_msg))

    # 2. 如果没有查到会话历史，则根据 request_id 进行平滑降级（只组装当前单次请求的内容）
    if not messages:
        row = await db.token_usage_logs.find_one({"request_id": request_id})
        if not row:
            raise HTTPException(status_code=404, detail="未找到对应的调用或会话记录")
        
        row_main_id = str(row.get("main_id") or "default")
        if row_main_id != own_main_id:
            raise HTTPException(status_code=403, detail="无权查看该记录")
        
        # 提取回复内容
        reply_content = ""
        response_payload = row.get("response_payload")
        if response_payload and isinstance(response_payload, dict):
            choices = response_payload.get("choices")
            if choices and isinstance(choices, list) and len(choices) > 0:
                msg_body = choices[0].get("message")
                if msg_body and isinstance(msg_body, dict):
                    reply_content = msg_body.get("content") or ""
            if not reply_content:
                reply_content = response_payload.get("output") or ""
        
        if not reply_content:
            reply_content = "暂无回复内容或回复格式无法解析"

        session_title = str(row.get("request_title_zh") or row.get("intent") or "单次调用详情")
        
        # 封装为单轮对话消息流
        created_at_val = _format_utc_datetime(row.get("created_at"))
        
        # 提问消息
        messages.append({
            "id": f"msg_user_{request_id}",
            "role": "user",
            "content": str(row.get("prompt") or ""),
            "plan": None,
            "progress": None,
            "documents": [],
            "images": [],
            "createdAt": created_at_val,
        })
        
        # 回复消息
        messages.append({
            "id": f"msg_ai_{request_id}",
            "role": "assistant",
            "content": reply_content,
            "plan": None,
            "progress": None,
            "documents": [],
            "images": [],
            "createdAt": created_at_val,
        })

    return {
        "sessionId": session_id_val,
        "title": session_title,
        "messages": messages,
    }
