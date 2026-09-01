from __future__ import annotations

import re
from typing import Any, Dict, Iterable

from app.llm.decision_turn.contracts import CommentaryReason, ModelCommentary, normalize_decision_commentary


_GENERIC_PATTERNS = (
    re.compile(r"^(正在|开始|即将)?(执行|处理|分析|规划|调用|生成|查询|搜索)(任务|请求|步骤|工具)?[。.!！]?$"),
    re.compile(r"^(已|已经)?(完成|结束)(执行|处理|分析|规划|调用|生成|查询|搜索)?(任务|请求|步骤|工具)?[。.!！]?$"),
    re.compile(r"^(working on|processing|analyzing|planning|executing|calling tools?)( the)?( task| request)?[.!]?$", re.I),
    re.compile(r"^(task|request|analysis|planning|execution)( is)? (complete|completed|done)[.!]?$", re.I),
)


def resolve_run_locale(messages: Iterable[Dict[str, Any]], explicit: Any = None) -> str:
    requested = str(explicit or "").strip().lower().replace("_", "-")
    if requested.startswith("zh"):
        return "zh-CN"
    if requested.startswith("en"):
        return "en-US"
    for message in reversed(list(messages or [])):
        if str((message or {}).get("role") or "").lower() != "user":
            continue
        text = str((message or {}).get("content") or "")
        return "zh-CN" if re.search(r"[\u4e00-\u9fff]", text) else "en-US"
    return "zh-CN"


def normalize_model_commentary(value: Any, *, locale: str) -> Dict[str, str] | None:
    return normalize_decision_commentary(value, locale=resolve_run_locale([], locale))


def make_runtime_commentary(value: Any, *, locale: str, turn_id: str = "") -> Dict[str, Any] | None:
    payload = normalize_model_commentary(value, locale=locale)
    if payload is None:
        return None
    if turn_id:
        payload["turn_id"] = str(turn_id)
    return {"type": "commentary", "content": payload}
