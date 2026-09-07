"""Compile model actions into safe, revision-bound execution segments."""
from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


OBSERVATION_BOUNDARY_TOOLS = frozenset({
    "browser_observe",
    "browser_read_text",
    "browser_screenshot",
})

_COMMIT_PURPOSES = frozenset({"send", "submit", "publish", "save", "create", "delete"})


def split_at_observation_boundary(
    actions: Sequence[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], str]:
    """Return the executable part before the first explicit observation.

    Every browser action returns control to the outer loop, which refreshes the
    live observation before planning again.  Consequently an observation tool
    following another action is a turn boundary, not part of an atomic sidecar
    plan.  If it is first, it alone is the next turn.
    """
    copied = [dict(action) for action in actions]
    for index, action in enumerate(copied):
        tool = str(action.get("tool") or "")
        if tool not in OBSERVATION_BOUNDARY_TOOLS:
            continue
        if index == 0:
            return [action], "observation_action_starts_new_turn"
        return copied[:index], "trailing_observation_deferred_to_next_turn"
    return copied, ""


def safe_first_action(
    actions: Sequence[Dict[str, Any]],
    observation: Observation,
) -> Dict[str, Any] | None:
    """Extract one non-commit action when a proposed multi-action plan is unsafe.

    This does not bypass the normal executor gates.  It only turns a serial but
    over-batched model proposal into one action followed by a fresh planner turn.
    """
    if not actions:
        return None
    first = actions[0]
    tool = str(first.get("tool") or "")
    args = first.get("args") if isinstance(first.get("args"), dict) else {}
    target = _target_for(args, observation)

    if tool == "browser_fill":
        return _copy(first) if target and target.get("editable") else None
    if tool == "browser_press":
        key = str(args.get("key") or "").lower()
        return _copy(first) if key in {"enter", "return"} and _is_search_target(target) else None
    if tool == "browser_click":
        return _copy(first) if _is_safe_activation_target(target) else None
    if tool == "browser_select":
        return _copy(first) if target and str(args.get("value") or "") else None
    if tool == "browser_scroll":
        return _copy(first) if str(args.get("direction") or "") else None
    if tool == "browser_wait_for":
        return _copy(first)
    if tool in OBSERVATION_BOUNDARY_TOOLS:
        return _copy(first)
    if tool == "browser_navigate":
        return _copy(first) if str(args.get("url") or "").strip() else None
    if tool == "browser_tab_new":
        return _copy(first)
    if tool in {"browser_back", "browser_forward"}:
        return _copy(first)
    return None


def _target_for(args: Dict[str, Any], observation: Observation) -> Dict[str, Any] | None:
    ref = str(args.get("ref") or "")
    if not ref:
        return None
    return next(
        (
            item for item in observation.elements
            if isinstance(item, dict) and str(item.get("ref") or "") == ref
        ),
        None,
    )


def _is_search_target(target: Dict[str, Any] | None) -> bool:
    return bool(target and (
        str(target.get("role") or "").lower() == "searchbox"
        or target.get("searchContext") is True
        or str(target.get("semanticPurpose") or "") == "search"
    ))


def _is_safe_activation_target(target: Dict[str, Any] | None) -> bool:
    if not target or target.get("visible") is False or target.get("disabled"):
        return False
    purpose = str(target.get("semanticPurpose") or "")
    if purpose in _COMMIT_PURPOSES:
        return False
    return bool(
        target.get("editable")
        or str(target.get("role") or "").lower()
        in {"button", "textbox", "searchbox", "combobox", "menuitem", "tab", "link"}
    )


def _copy(action: Dict[str, Any]) -> Dict[str, Any]:
    args = action.get("args") if isinstance(action.get("args"), dict) else {}
    return {"tool": str(action.get("tool") or ""), "args": dict(args)}


__all__ = [
    "OBSERVATION_BOUNDARY_TOOLS",
    "safe_first_action",
    "split_at_observation_boundary",
]
