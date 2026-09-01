from __future__ import annotations

from typing import Any, Dict, Iterable


def last_user_text_from_dict_messages(messages: Iterable[Dict[str, Any]] | None) -> str:
    for message in reversed(list(messages or [])):
        if str(message.get("role") or "").strip().lower() == "user":
            return str(message.get("content") or "")
    return ""


def last_user_text_from_langchain_messages(messages: Iterable[Any] | None) -> str:
    for message in reversed(list(messages or [])):
        if getattr(message, "type", "") == "human":
            return str(getattr(message, "content", "") or "").strip()
    return ""

