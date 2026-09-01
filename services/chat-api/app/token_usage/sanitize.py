from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List

from app.llm.types import Message


MAX_PROMPT_CHARS = 2000
MAX_TEXT_CHARS = 4000
MAX_JSON_CHARS = 12000

_REQUEST_TITLES: Dict[str, tuple[str, str]] = {
    "chat": ("对话", "Chat"),
    "compose": ("内容生成", "Compose"),
    "spreadsheet_compose": ("表格生成", "Spreadsheet Compose"),
    "planning": ("任务规划", "Planning"),
    "research_planning": ("研究规划", "Research Planning"),
    "research_query_refine": ("检索改写", "Research Query Refine"),
    "quality": ("质量评估", "Quality Review"),
    "editorial": ("编辑润色", "Editorial Rewrite"),
    "context_compaction": ("上下文压缩", "Context Compaction"),
    "intent_routing": ("意图路由", "Intent Routing"),
    "vision": ("图像理解", "Vision Understanding"),
    "volc_ark_search": ("联网检索", "Connected Search"),
    "knowledge_qa": ("内部知识问答", "Knowledge QA"),
}


def build_request_titles(stage: str, intent: str) -> tuple[str, str]:
    key = str(stage or "").strip().lower()
    if key in _REQUEST_TITLES:
        return _REQUEST_TITLES[key]
    token = str(intent or "").strip().lower()
    if token in _REQUEST_TITLES:
        return _REQUEST_TITLES[token]
    if key:
        pretty = key.replace("_", " ").strip().title()
        return pretty, pretty
    if token:
        pretty = token.replace("_", " ").strip().title()
        return pretty, pretty
    return "LLM 调用", "LLM Call"


def coerce_user_id(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def clip_text(value: Any, limit: int = MAX_TEXT_CHARS) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit] + "...(truncated)"


def extract_prompt(messages: Iterable[Message | Dict[str, Any] | Any]) -> str:
    for item in reversed(list(messages or [])):
        role = ""
        content = ""
        if isinstance(item, Message):
            role = str(item.role.value)
            content = _content_to_text(item.content)
        elif isinstance(item, dict):
            role = str(item.get("role") or "")
            content = _content_to_text(item.get("content"))
        else:
            role = str(getattr(item, "role", "") or "")
            content = _content_to_text(getattr(item, "content", ""))
        if role.lower() == "user":
            return clip_text(content, MAX_PROMPT_CHARS)
    return ""


def build_request_payload(
    *,
    messages: Iterable[Message | Dict[str, Any] | Any],
    kwargs: Dict[str, Any],
) -> Dict[str, Any]:
    payload = {
        "messages": [_message_summary(msg) for msg in list(messages or [])[-12:]],
        "options": _sanitize_json(kwargs),
    }
    return _limit_dict(payload, limit=MAX_JSON_CHARS)


def build_response_payload(raw_response: Any, fallback_content: Any = None) -> Dict[str, Any]:
    payload = _sanitize_json(raw_response)
    if not payload and fallback_content is not None:
        payload = {"content": clip_text(_content_to_text(fallback_content), MAX_TEXT_CHARS)}
    return _limit_dict(payload if isinstance(payload, dict) else {"data": payload}, limit=MAX_JSON_CHARS)


def _message_summary(message: Message | Dict[str, Any] | Any) -> Dict[str, Any]:
    if isinstance(message, Message):
        role = str(message.role.value)
        content = message.content
        tool_calls = message.tool_calls
    elif isinstance(message, dict):
        role = str(message.get("role") or "")
        content = message.get("content")
        tool_calls = message.get("tool_calls")
    else:
        role = str(getattr(message, "role", "") or "")
        content = getattr(message, "content", "")
        tool_calls = getattr(message, "tool_calls", None)
    summary: Dict[str, Any] = {
        "role": role,
        "content": clip_text(_content_to_text(content), 1200),
    }
    if tool_calls:
        summary["tool_calls"] = _sanitize_json(tool_calls)
    return summary


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict):
                if "text" in item:
                    parts.append(str(item.get("text") or ""))
                elif item.get("type") == "image_url":
                    parts.append("[image]")
                else:
                    parts.append(json.dumps(item, ensure_ascii=False, default=str))
            else:
                parts.append(str(item))
        return "\n".join([part for part in parts if part])
    if isinstance(content, dict):
        return json.dumps(content, ensure_ascii=False, default=str)
    return str(content or "")


def _sanitize_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return clip_text(value, MAX_TEXT_CHARS) if isinstance(value, str) else value
    if hasattr(value, "model_dump"):
        return _sanitize_json(value.model_dump())
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for idx, (key, item) in enumerate(value.items()):
            if idx >= 24:
                out["..."] = "truncated"
                break
            if "api_key" in str(key).lower() or "authorization" in str(key).lower():
                out[str(key)] = "***"
                continue
            out[str(key)] = _sanitize_json(item)
        return out
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        return [_sanitize_json(item) for item in items[:12]] + (["truncated"] if len(items) > 12 else [])
    return clip_text(value, MAX_TEXT_CHARS)


def _limit_dict(value: Dict[str, Any], *, limit: int) -> Dict[str, Any]:
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return value
    return {"truncated": True, "preview": text[:limit]}
