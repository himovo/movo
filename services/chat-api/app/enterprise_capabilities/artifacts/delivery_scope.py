"""Translate the tool delivery scope into authoritative artifact metadata."""

from __future__ import annotations

from typing import Any


def apply_delivery_scope(value: dict[str, Any], scope: Any) -> dict[str, Any]:
    result = dict(value or {})
    result.pop("url", None)
    result.pop("signed_url", None)
    normalized = str(scope or "final").strip().lower()
    if normalized == "intermediate":
        result["lifecycle"] = "intermediate"
        result["visibility"] = "internal"
    else:
        result.setdefault("lifecycle", "final")
        result.setdefault("visibility", "user")
    return result


def apply_result_delivery_scope(value: dict[str, Any], scope: Any) -> dict[str, Any]:
    """Apply one delivery decision to every artifact surface in a tool result."""
    result = dict(value or {})
    for key in ("documents", "images"):
        items = result.get(key)
        if isinstance(items, list):
            result[key] = [
                apply_delivery_scope(item, scope) if isinstance(item, dict) else item
                for item in items
            ]
    exported = result.get("exported_file")
    if isinstance(exported, dict):
        nested = dict(exported)
        for key in ("documents", "images"):
            items = nested.get(key)
            if isinstance(items, list):
                nested[key] = [
                    apply_delivery_scope(item, scope) if isinstance(item, dict) else item
                    for item in items
                ]
        result["exported_file"] = nested
    return result


__all__ = ["apply_delivery_scope", "apply_result_delivery_scope"]
