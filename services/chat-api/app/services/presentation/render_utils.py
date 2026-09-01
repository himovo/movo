"""Shared rendering utilities consumed by both html_renderer and pptx_compiler.

All rendering logic that touches the FreeformDeckBlueprint data model lives
here so both output backends stay in sync.  Individual renderers translate
these intermediate results into HTML or python-pptx calls — they never
re-derive style/z-order/coordinate logic independently.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

from app.services.presentation.contracts import FreeformBlock, FreeformDeckBlueprint


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SLIDE_W_PX = 1600
SLIDE_H_PX = 900

SLIDE_W_EMU = 12192000
SLIDE_H_EMU = 6858000


# ---------------------------------------------------------------------------
# Coordinate conversion
# ---------------------------------------------------------------------------


def norm_to_emu(x: float, y: float, w: float, h: float) -> Tuple[int, int, int, int]:
    """Convert normalised [0,1] coords to EMU."""
    return (
        int(x * SLIDE_W_EMU),
        int(y * SLIDE_H_EMU),
        max(1, int(w * SLIDE_W_EMU)),
        max(1, int(h * SLIDE_H_EMU)),
    )


def resolve_page_coords(
    block: FreeformBlock,
    parent_rect: Tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0),
) -> Tuple[float, float, float, float]:
    """Resolve a block's geometry to page-absolute normalised coords.

    Returns (x_page, y_page, w_page, h_page) in [0,1] space.
    """
    px, py, pw, ph = parent_rect
    pw = max(pw, 0.0001)
    ph = max(ph, 0.0001)

    coord_space = str(getattr(block, "coordinate_space", "page") or "page").strip().lower()
    if coord_space == "parent":
        return (
            px + float(block.x or 0.0) * pw,
            py + float(block.y or 0.0) * ph,
            float(block.w or 0.0) * pw,
            float(block.h or 0.0) * ph,
        )
    return (
        float(block.x or 0.0),
        float(block.y or 0.0),
        float(block.w or 0.0),
        float(block.h or 0.0),
    )


def resolve_line_endpoints(
    block: FreeformBlock,
    parent_rect: Tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0),
) -> Tuple[float, float, float, float]:
    """Return (x1, y1, x2, y2) in page-absolute normalised coords for a line block."""
    px, py, pw, ph = parent_rect
    pw = max(pw, 0.0001)
    ph = max(ph, 0.0001)
    coord_space = str(getattr(block, "coordinate_space", "page") or "page").strip().lower()

    if coord_space == "parent":
        x1 = px + float(block.x or 0.0) * pw
        y1 = py + float(block.y or 0.0) * ph
        x2 = px + float(block.x2 or block.x or 0.0) * pw
        y2 = py + float(block.y2 or block.y or 0.0) * ph
    else:
        x1 = float(block.x or 0.0)
        y1 = float(block.y or 0.0)
        x2 = float(block.x2 if block.x2 is not None else block.x or 0.0)
        y2 = float(block.y2 if block.y2 is not None else block.y or 0.0)
    return x1, y1, x2, y2


# ---------------------------------------------------------------------------
# Z-order / render order
# ---------------------------------------------------------------------------


def render_order(shape: FreeformBlock) -> Tuple[int, str]:
    """Sort key for visual stacking order.

    Primary key is the block's ``z_index``.  When z_index is 0 a type-based
    fallback is used (see the table below).  The fallback never produces a
    value >5 so text at z=5 always wins against a fallback panel.

    Fallback hierarchy:
        0  full-page background rectangles (>=80% area)
        1  decorative panels / hero / band rectangles
        2  image / chart
        3  circle / group
        4  connector lines
        5  standalone text_box / icon
    """
    z = int(shape.z_index or 0)
    if z == 0:
        z_raw = dict(shape.style or {}).get("z_index")
        try:
            z = int(z_raw)
        except Exception:
            z = 0
    if z != 0:
        return z, str(shape.id or "")

    shape_type = str(shape.type or "").strip().lower()
    role = str(getattr(shape, "role", "") or "").strip().lower()

    if role in {"background", "surface"}:
        return 0, str(shape.id or "")
    if shape_type == "rectangle":
        area = float(shape.w or 0) * float(shape.h or 0)
        if area >= 0.80:
            return 0, str(shape.id or "")
        return 1, str(shape.id or "")
    if shape_type in {"image", "chart"}:
        return 2, str(shape.id or "")
    if shape_type in {"circle", "group"}:
        return 3, str(shape.id or "")
    if shape_type == "line":
        return 4, str(shape.id or "")
    if shape_type in {"text_box", "icon"}:
        return 5, str(shape.id or "")
    return 3, str(shape.id or "")


# ---------------------------------------------------------------------------
# Chart spec resolution
# ---------------------------------------------------------------------------


def resolve_chart_spec(shape: FreeformBlock) -> Tuple[str, Dict[str, Any]]:
    """Extract (chart_type, chart_payload) from a chart block.

    Normalises the many ways chart data can be specified (chart_data field,
    style dict, JSON content string) into a single (type, payload) pair.
    """
    chart_type = str(getattr(shape, "chart_type", "") or "").strip().lower()
    style = dict(shape.style or {})
    if not chart_type:
        chart_type = str(style.get("chart_type") or style.get("chart_kind") or "").strip().lower()
    alias = {
        "line_chart": "line", "line-chart": "line", "linechart": "line",
        "bar_chart": "bar", "bar-chart": "bar", "barchart": "bar",
        "pie_chart": "pie", "pie-chart": "pie", "piechart": "pie",
    }
    chart_type = alias.get(chart_type, chart_type)

    payload: Dict[str, Any] = {}
    if isinstance(getattr(shape, "chart_data", None), dict):
        payload.update(dict(shape.chart_data or {}))
    if not payload and isinstance(style.get("chart_data"), dict):
        payload.update(dict(style.get("chart_data") or {}))
    if not payload:
        content = str(shape.content or "").strip()
        if content.startswith("{") and content.endswith("}"):
            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    payload.update(parsed)
            except Exception:
                pass
    if not payload:
        for key in ("title", "subtitle", "categories", "series", "values", "y_axis_label", "x_axis_label"):
            if key in style:
                payload[key] = style.get(key)

    payload["title"] = str(payload.get("title") or shape.content or "").strip()
    if not chart_type:
        if isinstance(payload.get("values"), list) and payload.get("values"):
            chart_type = "pie"
        elif isinstance(payload.get("series"), list) and payload.get("series"):
            chart_type = "bar"
    if chart_type not in {"line", "bar", "pie"}:
        chart_type = ""
    return chart_type, payload


# ---------------------------------------------------------------------------
# Style resolution
# ---------------------------------------------------------------------------


def parse_hex_color(value: str) -> Tuple[int, int, int] | None:
    """Parse '#rrggbb' or '#rgb' to (r, g, b).  Returns None on failure."""
    token = str(value or "").strip().lstrip("#")
    if len(token) == 3:
        token = "".join(ch * 2 for ch in token)
    match = re.search(r"[0-9a-fA-F]{6}", token)
    if not match:
        return None
    hex6 = match.group(0)
    return (int(hex6[0:2], 16), int(hex6[2:4], 16), int(hex6[4:6], 16))


def parse_rgba_color(value: str) -> Tuple[int, int, int] | None:
    """Parse 'rgba(r, g, b, a)' or 'rgb(r, g, b)' to (r, g, b)."""
    m = re.match(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", str(value or ""))
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def resolve_color_rgb(value: str) -> Tuple[int, int, int] | None:
    """Best-effort parse any CSS color string to (r, g, b)."""
    if not value or value.strip().lower() in {"transparent", "none", "inherit", "initial"}:
        return None
    rgb = parse_hex_color(value)
    if rgb:
        return rgb
    return parse_rgba_color(value)


GradientStop = Tuple[float, Tuple[int, int, int]]  # (position 0-1, rgb)


def parse_linear_gradient(value: str) -> Tuple[float, List[GradientStop]] | None:
    """Parse CSS ``linear-gradient(...)`` into (angle_degrees, stops).

    Supports:
      - ``linear-gradient(135deg, #aaa 0%, #bbb 100%)``
      - ``linear-gradient(to right, #aaa, #bbb)``
      - ``linear-gradient(#aaa, #bbb)``  (default 180deg)

    Returns None if *value* is not a gradient.
    """
    value = str(value or "").strip()
    m = re.match(r"linear-gradient\s*\((.+)\)\s*$", value, re.IGNORECASE)
    if not m:
        return None
    inner = m.group(1).strip()

    # Split on top-level commas (not inside parens)
    parts: List[str] = []
    depth = 0
    buf: List[str] = []
    for ch in inner:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
            continue
        buf.append(ch)
    if buf:
        parts.append("".join(buf).strip())

    if not parts:
        return None

    angle = 180.0
    color_parts = parts
    first = parts[0].strip().lower()

    # Check if first part is an angle or direction
    angle_match = re.match(r"(-?\d+(?:\.\d+)?)\s*deg", first)
    if angle_match:
        angle = float(angle_match.group(1))
        color_parts = parts[1:]
    elif first.startswith("to "):
        direction_map = {
            "to top": 0, "to right": 90, "to bottom": 180, "to left": 270,
            "to top right": 45, "to bottom right": 135,
            "to bottom left": 225, "to top left": 315,
        }
        angle = direction_map.get(first, 180.0)
        color_parts = parts[1:]

    stops: List[GradientStop] = []
    for idx, part in enumerate(color_parts):
        part = part.strip()
        # Try to extract position percentage
        pos_match = re.search(r"(\d+(?:\.\d+)?)\s*%\s*$", part)
        if pos_match:
            position = float(pos_match.group(1)) / 100.0
            color_str = part[:pos_match.start()].strip()
        else:
            position = idx / max(1, len(color_parts) - 1) if len(color_parts) > 1 else 0.0
            color_str = part

        rgb = resolve_color_rgb(color_str)
        if rgb:
            stops.append((position, rgb))

    if len(stops) < 2:
        return None
    return angle, stops


def resolve_font_weight(value: Any) -> bool:
    """Return True if the value represents bold."""
    if isinstance(value, bool):
        return value
    s = str(value or "").strip().lower()
    return s in {"bold", "700", "800", "900", "semibold", "600"}


def resolve_font_size_pt(value: Any) -> float | None:
    """Extract font size in **pt** from a blueprint style value.

    Blueprint ``font_size`` values are CSS px (designed for a 1600×900 HTML
    canvas at 96 DPI).  PowerPoint uses points (1 pt = 1/72 in = 96/72 px).
    So we convert: ``pt = px × 72 / 96 = px × 0.75``.
    """
    if value is None or value == "":
        return None
    px: float
    if isinstance(value, (int, float)):
        px = float(value)
    else:
        m = re.search(r"(\d+(?:\.\d+)?)", str(value))
        if not m:
            return None
        px = float(m.group(1))
    return max(1.0, px * 0.75)


def resolve_text_align(value: Any) -> str:
    """Normalise text-align to one of left/center/right/justify."""
    s = str(value or "").strip().lower()
    if s in {"center", "middle"}:
        return "center"
    if s in {"right", "end"}:
        return "right"
    if s == "justify":
        return "justify"
    return "left"


def resolve_vertical_align(value: Any) -> str:
    """Normalise vertical-align to top/middle/bottom."""
    s = str(value or "").strip().lower()
    if s in {"center", "middle"}:
        return "middle"
    if s in {"bottom", "end"}:
        return "bottom"
    return "top"


def infer_text_vertical_align(
    *,
    content: Any,
    style: Dict[str, Any] | None,
    box_height_norm: Any,
    canvas_height_px: float = 900.0,
) -> str:
    """Infer vertical alignment for compact single-line text boxes.

    Many image-native blocks omit ``vertical_align`` even for number badges,
    pills, and centered labels. Rendering them as top-aligned makes the text
    visibly stick to the upper edge of the box. We only infer ``middle`` for
    compact single-line centered text boxes; everything else stays top-aligned.
    """
    style = dict(style or {})
    explicit = style.get("vertical_align")
    if explicit not in (None, ""):
        return resolve_vertical_align(explicit)

    text = str(content or "").strip()
    if not text or "\n" in text:
        return "top"

    text_align = resolve_text_align(style.get("text_align"))
    if text_align != "center":
        return "top"

    try:
        box_px = max(0.0, float(box_height_norm or 0.0) * float(canvas_height_px))
    except Exception:
        return "top"
    if box_px <= 0:
        return "top"

    raw_font = style.get("font_size")
    font_px = 18.0
    if raw_font not in (None, ""):
        m = re.search(r"(\d+(?:\.\d+)?)", str(raw_font))
        if m:
            try:
                font_px = max(8.0, float(m.group(1)))
            except Exception:
                font_px = 18.0

    raw_lh = style.get("line_height", 1.2)
    line_height_px = font_px * 1.2
    try:
        lh = float(str(raw_lh).replace("px", "").strip())
        if lh <= 4.0:
            line_height_px = font_px * max(1.0, lh)
        else:
            line_height_px = lh
    except Exception:
        pass

    # Middle-align only when the box is a compact single-line container,
    # e.g. badges, pills, centered labels, or short boxed metrics.
    if box_px <= line_height_px * 1.9:
        return "middle"
    return "top"


def chart_theme_from_deck(deck: FreeformDeckBlueprint) -> Dict[str, Any]:
    """Extract chart colour theme from deck for chart renderers."""
    return {
        "accent_color": str(getattr(deck.theme, "accent_color", "") or "#2563eb"),
        "title_color": str(getattr(deck.theme, "title_color", "") or "#0f172a"),
        "body_color": str(getattr(deck.theme, "body_color", "") or "#334155"),
        "muted_color": str(getattr(deck.theme, "muted_color", "") or "#64748b"),
        "surface_background": str(getattr(deck.theme, "surface_background", "") or "#ffffff"),
        "page_background": str(getattr(deck.theme, "page_background", "") or "#ffffff"),
    }


def resolve_block_content(block: FreeformBlock) -> str:
    """Get displayable text content from a block, checking style fallbacks."""
    content = str(block.content or "")
    if not content.strip() and str(block.type or "").strip().lower() in {"text_box", "title", "body"}:
        style = dict(block.style or {})
        for key in ("text", "label", "title", "subtitle", "value", "content"):
            candidate = style.get(key)
            if candidate is not None and str(candidate).strip():
                return str(candidate)
    return content
