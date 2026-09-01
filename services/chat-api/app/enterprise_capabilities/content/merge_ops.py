from __future__ import annotations

from typing import Any, Dict


def deep_overlay_non_empty(base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, val in incoming.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = deep_overlay_non_empty(dict(out.get(key) or {}), val)
            continue
        if isinstance(val, list):
            if val:
                out[key] = val
            continue
        if val in ("", None):
            continue
        out[key] = val
    return out

