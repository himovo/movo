"""Resolve a browser mutation decision to an observed semantic element."""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, Optional

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


def resolve_effect_target(decision: Decision, observation: Observation) -> Optional[Dict[str, Any]]:
    elements = [item for item in observation.elements if isinstance(item, dict)]
    args = decision.args or {}
    if decision.tool == "browser_paste_image":
        ref = str(args.get("editor_ref") or "").strip()
        return next((item for item in elements if str(item.get("ref") or "").strip() == ref), None)
    if decision.tool == "browser_click":
        ref = str(args.get("ref") or "").strip()
        return next((item for item in elements if str(item.get("ref") or "").strip() == ref), None)
    if decision.tool != "browser_click_at":
        return None
    try:
        point = (float(args.get("x")), float(args.get("y")))
    except (TypeError, ValueError):
        return None
    return resolve_coordinate_target(elements, point)


def resolve_coordinate_target(
    elements: Iterable[Dict[str, Any]],
    point: tuple[float, float],
    *,
    editable_only: bool = False,
    tolerance: float = 36.0,
) -> Optional[Dict[str, Any]]:
    """Resolve a screenshot coordinate against the latest DOM snapshot.

    DOM observations expose element centres, not top-left coordinates. Prefer
    the smallest element whose box contains the point, then use a bounded
    centre-distance fallback. This lets coordinate actions inherit a live ref
    instead of mutating whichever element happens to be under an old pixel.
    """
    candidates = [
        item for item in elements
        if isinstance(item, dict)
        and item.get("visible") is not False
        and item.get("disabled") is not True
        and (not editable_only or item.get("editable") is True)
    ]
    containing: list[tuple[float, int, Dict[str, Any]]] = []
    for item in candidates:
        box = _element_box(item)
        if box is None:
            continue
        left, top, right, bottom = box
        if left <= point[0] <= right and top <= point[1] <= bottom:
            area = max(1.0, (right - left) * (bottom - top))
            containing.append((area, _interaction_rank(item), item))
    if containing:
        return min(containing, key=lambda entry: (entry[0], -entry[1]))[2]
    return _nearest_visible_element(candidates, point, tolerance=tolerance)


def _nearest_visible_element(
    elements: Iterable[Dict[str, Any]],
    point: tuple[float, float],
    *,
    tolerance: float = 36.0,
) -> Optional[Dict[str, Any]]:
    candidates: list[tuple[float, Dict[str, Any]]] = []
    for item in elements:
        if item.get("visible") is False or item.get("disabled") is True:
            continue
        try:
            distance = math.hypot(float(item.get("x")) - point[0], float(item.get("y")) - point[1])
        except (TypeError, ValueError):
            continue
        if distance <= tolerance:
            candidates.append((distance, item))
    return min(candidates, key=lambda pair: pair[0])[1] if candidates else None


def _element_box(item: Dict[str, Any]) -> Optional[tuple[float, float, float, float]]:
    try:
        center_x = float(item.get("x"))
        center_y = float(item.get("y"))
        width = float(item.get("width"))
        height = float(item.get("height"))
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return (
        center_x - width / 2,
        center_y - height / 2,
        center_x + width / 2,
        center_y + height / 2,
    )


def _interaction_rank(item: Dict[str, Any]) -> int:
    if item.get("editable"):
        return 3
    if str(item.get("role") or "").casefold() in {"button", "link", "menuitem", "checkbox", "radio"}:
        return 2
    if item.get("href"):
        return 1
    return 0


__all__ = ["resolve_coordinate_target", "resolve_effect_target"]
