from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Dict


_request_context: ContextVar[Dict[str, Any]] = ContextVar("request_context", default={})


def set_request_context(payload: Dict[str, Any] | None) -> Dict[str, Any]:
    previous = dict(_request_context.get({}) or {})
    _request_context.set(dict(payload or {}))
    return previous


def merge_request_context(payload: Dict[str, Any] | None) -> Dict[str, Any]:
    previous = dict(_request_context.get({}) or {})
    merged = dict(previous)
    for key, value in dict(payload or {}).items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        merged[str(key)] = value
    _request_context.set(merged)
    return previous


def reset_request_context(previous: Dict[str, Any] | None) -> None:
    _request_context.set(dict(previous or {}))


def get_request_context() -> Dict[str, Any]:
    return dict(_request_context.get({}) or {})
