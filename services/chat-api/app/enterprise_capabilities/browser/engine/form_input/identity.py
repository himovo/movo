from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any, Dict, Iterable, Optional


def visible_text(value: Any) -> str:
    """Normalize DOM text without letting invisible format chars become labels."""
    text = "".join(
        char for char in str(value or "")
        if unicodedata.category(char) != "Cf"
    )
    return re.sub(r"\s+", " ", text).strip()


def stable_field_key(element: Dict[str, Any], occurrence: int = 0) -> str:
    """Build identity from DOM structure, never from placeholder or value."""
    frame_depth = int(element.get("frameDepth") or 0)
    selector = str(element.get("selector") or "").strip()
    if selector:
        return f"selector:{frame_depth}:{selector}"
    backend_node_id = element.get("backendNodeId")
    if backend_node_id not in (None, ""):
        return f"backend:{frame_depth}:{backend_node_id}"

    structural = "\0".join((
        str(frame_depth),
        str(element.get("role") or "").strip().casefold(),
        str(element.get("tag") or "").strip().casefold(),
        str(element.get("type") or "").strip().casefold(),
        str(max(0, occurrence)),
    ))
    return "field_" + hashlib.sha1(structural.encode("utf-8")).hexdigest()[:14]


def field_label(element: Dict[str, Any], fallback: str = "") -> str:
    """Return a stable label; placeholder remains a hint, not field identity."""
    for key in ("name", "description", "text", "type"):
        value = visible_text(element.get(key))
        if value:
            return value[:120]
    return fallback or "未命名字段"


def find_field(
    elements: Iterable[Dict[str, Any]],
    target: Dict[str, Any],
    fallback_ref: str = "",
) -> Optional[Dict[str, Any]]:
    candidates = [
        item for item in elements if isinstance(item, dict)
        and int(item.get("frameDepth") or 0) == int(target.get("frameDepth") or 0)
        and all(not target.get(key) or item.get(key) == target[key]
                for key in ("frameId", "scopeSelector"))
    ]
    selector = str(target.get("selector") or "").strip()
    frame_depth = int(target.get("frameDepth") or 0)
    backend_node_id = target.get("backendNodeId")
    if backend_node_id not in (None, ""):
        matches = [
            item for item in candidates
            if item.get("backendNodeId") == backend_node_id
            and int(item.get("frameDepth") or 0) == frame_depth
        ]
        if matches:
            return matches[0] if len(matches) == 1 else None
    if selector:
        matches = [item for item in candidates
                   if str(item.get("selector") or "").strip() == selector]
        return matches[0] if len(matches) == 1 else None
    # Never reinterpret a stale ref after a known node disappeared.
    if backend_node_id not in (None, ""):
        return None
    if fallback_ref:
        matches = [
            item for item in candidates
            if str(item.get("ref") or "") == fallback_ref
        ]
        return matches[0] if len(matches) == 1 else None
    return None


__all__ = ["field_label", "find_field", "stable_field_key", "visible_text"]
