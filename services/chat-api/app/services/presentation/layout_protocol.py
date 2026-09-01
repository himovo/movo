from __future__ import annotations

from typing import FrozenSet, Tuple


MIN_LINE_LENGTH: float = 0.01
SIBLING_OVERLAP_RATIO_THRESHOLD: float = 0.35
TEXT_TEXT_OVERLAP_RATIO_THRESHOLD: float = 0.55
SEVERE_OVERLAP_AREA_THRESHOLD: float = 0.003
OVERLAP_HARD_COUNT_THRESHOLD: int = 3
CHILD_OUTSIDE_CONTAINER_RATIO_LIMIT: float = 0.05

HARD_QUALITY_ISSUES: FrozenSet[str] = frozenset(
    {
        "children_outside_container",
        "overlapping_siblings",
        "text_box_too_narrow",
        "text_box_too_short",
        "degenerate_lines",
        "line_too_short",
        "line_missing_endpoints",
        "out_of_bounds_geometry",
    }
)


def text_geometry_requirements(text: str, *, font_size: float | None = None) -> Tuple[float, float]:
    text_len = len(str(text or "").replace("\n", "").replace("<br/>", "").strip())
    min_w = 0.10
    min_h = 0.045
    if text_len >= 8:
        min_w = 0.14
        min_h = 0.055
    if text_len >= 16:
        min_w = 0.18
        min_h = 0.07
    if text_len >= 36:
        min_w = 0.24
        min_h = 0.10
    if text_len >= 72:
        min_w = 0.30
        min_h = 0.14
    fs = float(font_size) if font_size not in (None, "") else 22.0
    # Scale minimum geometry with font size to avoid readability false positives.
    # 22px is the baseline of previous heuristics.
    scale = max(0.70, min(2.20, fs / 22.0))
    min_w = min(0.92, max(0.08, min_w * (0.88 + 0.22 * scale)))
    min_h = min(0.70, max(0.04, min_h * scale))
    return min_w, min_h


def normalize_line_route(route: str) -> str:
    token = str(route or "").strip().lower()
    if token in {"h", "horizontal"}:
        return "h"
    if token in {"v", "vertical"}:
        return "v"
    return "auto"
