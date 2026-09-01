"""Normalize partially structured effect-discovery results.

The model decides semantic fields. Values already present in the clicked DOM
target, such as the action label, are deterministic context and must not make
the entire contract unusable when the model omits them.
"""
from __future__ import annotations

from typing import Any, Dict


_SIDE_EFFECTS = {"none", "write", "destructive", "external"}
_NON_COMMIT_FAMILIES = {"navigate", "navigation", "search", "query", "filter", "open"}
_COMMIT_FAMILIES = {
    "create",
    "update",
    "delete",
    "submit",
    "publish",
    "send",
    "save",
    "transition",
}


def normalize_discovered_contract(
    raw: Dict[str, Any],
    *,
    target_label: str,
) -> Dict[str, Any]:
    data = dict(raw or {})
    action_name = str(data.get("action_name") or "").strip()
    operation_family = str(data.get("operation_family") or "custom").strip().lower() or "custom"
    side_effect = str(data.get("side_effect") or "").strip().lower()
    explicit_commit = data.get("is_commit")

    if isinstance(explicit_commit, bool):
        is_commit = explicit_commit
    elif operation_family in _NON_COMMIT_FAMILIES or side_effect == "none":
        is_commit = False
    else:
        is_commit = operation_family in _COMMIT_FAMILIES or side_effect in {
            "write",
            "destructive",
            "external",
        }

    if side_effect not in _SIDE_EFFECTS:
        side_effect = "write" if is_commit else "none"
    elif not is_commit:
        side_effect = "none"
    elif side_effect == "none":
        side_effect = "write"

    return {
        **data,
        "action_name": action_name or str(target_label or "").strip() or "unknown action",
        "operation_family": operation_family,
        "entity": str(data.get("entity") or "").strip(),
        "side_effect": side_effect,
        "is_commit": is_commit,
        "completes_goal": _bool_value(data.get("completes_goal")),
        "fingerprint": _dict_value(data.get("fingerprint")),
        "expected_effects": _string_list(data.get("expected_effects")),
        "verification_hints": _string_list(data.get("verification_hints")),
    }


def _dict_value(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in {"1", "true", "yes"}


__all__ = ["normalize_discovered_contract"]
