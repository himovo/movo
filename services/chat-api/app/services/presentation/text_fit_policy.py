from __future__ import annotations

import math
from typing import Any, Dict

from app.services.presentation.text_box_style import parse_css_padding


def fit_text_style_to_box(
    *, content: str, box_w: float, box_h: float, style: Dict[str, Any], floor: float
) -> Dict[str, Any]:
    """Keep readable type proportionate to its authored box without reflowing layout."""
    out = dict(style or {})
    if not str(content or "").strip() or box_w <= 0 or box_h <= 0:
        return out
    requested = _number(out.get("font_size"), floor)
    line_height = max(0.9, min(2.0, _number(out.get("line_height"), 1.2)))
    top, right, bottom, left = parse_css_padding(out.get("padding"))
    width_px = max(12.0, box_w * 1600.0 - left - right)
    height_px = max(12.0, box_h * 900.0 - top - bottom)
    safe = _largest_fitting_size(
        str(content or "").replace("\\n", "\n"), width_px, height_px, line_height
    )
    # ``floor`` is semantic (headline/body/label), while ``safe`` is only a
    # geometric estimate.  Letting the estimator undercut the semantic floor
    # is how readable 22px copy became 14px timeline dust in the final render.
    # When the authored box is too small we keep projection-readable type and
    # let the authoring prompt/auto-fit contract allocate a larger box.
    desired = max(float(floor), requested)
    out["font_size"] = round(min(desired, safe) if safe >= floor else float(floor), 1)
    return out


def _largest_fitting_size(text: str, width: float, height: float, line_height: float) -> float:
    low, high = 10.0, 96.0
    for _ in range(12):
        candidate = (low + high) / 2.0
        if _estimated_height(text, width, candidate, line_height) <= height:
            low = candidate
        else:
            high = candidate
    return low


def _estimated_height(text: str, width: float, font_size: float, line_height: float) -> float:
    total_lines = 0
    for paragraph in text.splitlines() or [""]:
        units = sum(1.0 if ord(char) > 255 else 0.56 for char in paragraph) or 0.5
        chars_per_line = max(1.0, width / max(1.0, font_size))
        total_lines += max(1, math.ceil(units / chars_per_line))
    return total_lines * font_size * line_height


def _number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


__all__ = ["fit_text_style_to_box"]
