from __future__ import annotations

from typing import Any, Dict

from app.infrastructure.request_context import get_request_context


CONTEXT_FIELDS = (
    "http_request_id",
    "request_id",
    "message_id",
    "session_id",
    "user_id",
    "main_id",
    "trace_id",
    "run_id",
    "node_id",
    "span_id",
    "parent_span_id",
)


def current_log_context() -> Dict[str, Any]:
    ctx = get_request_context()
    out: Dict[str, Any] = {}
    for key in CONTEXT_FIELDS:
        value = ctx.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        out[key] = value
    return out


def compact_context(payload: Dict[str, Any] | None) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in dict(payload or {}).items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        out[str(key)] = value
    return out
