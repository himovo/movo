from __future__ import annotations

import re
from typing import Any

from app.core.db import get_db


def compact_request_text(value: str, limit: int = 100) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) > limit:
        return text[:limit] + "..."
    return text


def extract_user_question_from_prompt(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    match = re.search(r"用户问题：\s*(.*?)\s*(?:内部知识候选：|$)", text, flags=re.S)
    if match:
        return compact_request_text(match.group(1), 100)
    return compact_request_text(text, 100)


async def load_user_request_texts(rows: list[dict[str, Any]], main_id: str) -> dict[str, str]:
    request_ids = []
    for row in rows:
        request_id = str(row.get("user_request_id") or "").strip()
        if request_id and request_id not in request_ids:
            request_ids.append(request_id)
    if not request_ids:
        return {}

    db = get_db()
    assistant_rows = await db.chat_messages.find(
        {"main_id": main_id, "message_id": {"$in": request_ids}, "message_type": {"$ne": "context_summary"}},
        {"message_id": 1, "session_id": 1, "seq": 1},
    ).to_list(length=len(request_ids))

    result: dict[str, str] = {}
    for assistant in assistant_rows:
        message_id = str(assistant.get("message_id") or "").strip()
        session_id = assistant.get("session_id")
        seq = int(assistant.get("seq") or 0)
        if not message_id or not session_id or seq <= 0:
            continue
        user_msg = await db.chat_messages.find_one(
            {
                "main_id": main_id,
                "session_id": session_id,
                "role": "user",
                "message_type": {"$ne": "context_summary"},
                "seq": {"$lt": seq},
            },
            {"content": 1},
            sort=[("seq", -1)],
        )
        content = str((user_msg or {}).get("content") or "").strip()
        if content:
            result[message_id] = compact_request_text(content, 100)
    return result


async def load_execution_statuses(rows: list[dict[str, Any]], main_id: str) -> dict[str, str]:
    request_ids = []
    for row in rows:
        request_id = str(row.get("_id") or row.get("user_request_id") or "").strip()
        if request_id and request_id not in request_ids:
            request_ids.append(request_id)
    if not request_ids:
        return {}
    db = get_db()
    docs = await db.execution_logs.find(
        {"main_id": main_id, "message_id": {"$in": request_ids}},
        {"message_id": 1, "status": 1},
    ).to_list(length=len(request_ids))
    return {
        str(row.get("message_id") or "").strip(): str(row.get("status") or "").strip()
        for row in docs
        if str(row.get("message_id") or "").strip()
    }
