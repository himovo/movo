"""Size-bound tool results without discarding their semantic contract."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any


_HEAVY_KEYS = {
    "screenshot", "screenshot_base64", "image_base64", "raw_html", "html",
    "accessibility_tree", "dom_snapshot",
}
_IMPORTANT_EVENT_TYPES = {
    "intervention_required", "subagent_done", "runtime_status", "answer", "activity",
}
_SUMMARY_KEYS = ("responseSummary", "summary", "message", "reason", "error")


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":")).encode()


def _summary(value: Any) -> str:
    if not isinstance(value, Mapping):
        return ""
    for key in _SUMMARY_KEYS:
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    for key in ("browser_result", "browser_receipt", "artifact", "plugin_result"):
        nested = _summary(value.get(key))
        if nested:
            return nested
    return ""


def _compact(value: Any, *, max_string: int, max_items: int, depth: int = 0, key: str = "") -> Any:
    if depth >= 8:
        return "[depth limited]"
    if isinstance(value, str):
        return value if len(value) <= max_string else value[:max_string] + "…"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Mapping):
        compacted: dict[str, Any] = {}
        for index, (raw_key, nested) in enumerate(value.items()):
            item_key = str(raw_key)
            if item_key in _HEAVY_KEYS:
                continue
            if index >= 80:
                compacted["_omitted_fields"] = len(value) - index
                break
            compacted[item_key] = _compact(
                nested, max_string=max_string, max_items=max_items, depth=depth + 1, key=item_key
            )
        return compacted
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        items = list(value)
        selected = (
            [item for item in items if isinstance(item, Mapping) and str(item.get("type") or "") in _IMPORTANT_EVENT_TYPES][-10:]
            if key == "domain_events" else items[:max_items]
        )
        compacted = [
            _compact(item, max_string=max_string, max_items=max_items, depth=depth + 1)
            for item in selected
        ]
        if len(selected) < len(items):
            compacted.append({"_omitted_items": len(items) - len(selected)})
        return compacted
    return str(value)[:max_string]


def compact_tool_result(result: dict[str, Any], *, max_bytes: int = 64 * 1024) -> dict[str, Any]:
    """Keep actionable state and a bounded preview when a tool result is large."""
    normalized = json.loads(_json_bytes(result))
    encoded = _json_bytes(normalized)
    if len(encoded) <= max_bytes:
        return normalized

    original_bytes = len(encoded)
    for max_string, max_items in ((8_000, 20), (3_000, 10), (1_000, 5)):
        compacted = _compact(normalized, max_string=max_string, max_items=max_items)
        compacted["truncated"] = True
        compacted["originalBytes"] = original_bytes
        compacted.setdefault("responseSummary", _summary(normalized)[:8_000])
        if len(_json_bytes(compacted)) <= max_bytes:
            return compacted

    keep = (
        "success", "status", "operation", "message", "reason", "error",
        "responseSummary", "intervention_suspension", "browser_receipt",
        "browser_result", "artifact", "documents", "failures", "total",
    )
    fallback = {
        key: _compact(normalized[key], max_string=1_000, max_items=3)
        for key in keep if key in normalized
    }
    fallback.setdefault("success", bool(normalized.get("success", True)))
    fallback["truncated"] = True
    fallback["originalBytes"] = original_bytes
    fallback.setdefault("responseSummary", _summary(normalized)[:4_000])
    if not fallback["responseSummary"]:
        fallback["preview"] = _compact(normalized, max_string=500, max_items=2)
    return fallback


__all__ = ["compact_tool_result"]
