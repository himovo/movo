from __future__ import annotations

from typing import Any


def element_is_usable(element: object, *, require_hit_target: bool = True) -> bool:
    if not isinstance(element, dict):
        return False
    if element.get("visible", True) is False or element.get("disabled") is True:
        return False
    if element.get("inViewport", element.get("in_viewport", True)) is False:
        return False
    if require_hit_target and element.get("hitTestable", element.get("hit_testable", True)) is False:
        return False
    return True


def logical_action_succeeded(tool: str, result: Any, diagnostics: object) -> bool:
    """Distinguish transport success from the tool's logical outcome."""

    payload = result if isinstance(result, dict) else {}
    diag = diagnostics if isinstance(diagnostics, dict) else {}
    if tool == "browser_wait_for":
        return payload.get("matched") is True or (
            payload.get("waited") is True and payload.get("mode") == "delay"
        )
    if tool == "browser_select":
        selection = diag.get("select")
        return isinstance(selection, dict) and selection.get("confirmed") is True
    if tool == "browser_scroll":
        scroll = diag.get("scroll")
        return isinstance(scroll, dict) and scroll.get("progressed") is True
    return True


def actionable_surface_identity(element: dict[str, Any]) -> tuple[str, ...]:
    return (
        str(element.get("selector") or ""),
        str(element.get("role") or ""),
        str(element.get("name") or element.get("text") or ""),
        str(element.get("scopeId") or element.get("scope_id") or ""),
    )


__all__ = [
    "actionable_surface_identity",
    "element_is_usable",
    "logical_action_succeeded",
]
