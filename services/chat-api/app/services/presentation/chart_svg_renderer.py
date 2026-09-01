from __future__ import annotations

import html
from typing import Any, Dict, List


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    token = str(value or "").strip().lstrip("#")
    if len(token) == 3:
        token = "".join(ch * 2 for ch in token)
    if len(token) != 6:
        token = "2563eb"
    return tuple(int(token[idx: idx + 2], 16) for idx in range(0, 6, 2))


def _rgba(value: str, alpha: float) -> str:
    r, g, b = _hex_to_rgb(value)
    return f"rgba({r}, {g}, {b}, {max(0.0, min(1.0, alpha)):.3f})"


def _mix(color_a: str, color_b: str, ratio: float) -> str:
    ratio = max(0.0, min(1.0, ratio))
    a = _hex_to_rgb(color_a)
    b = _hex_to_rgb(color_b)
    mixed = tuple(int(round(a[idx] * (1.0 - ratio) + b[idx] * ratio)) for idx in range(3))
    return "#{:02x}{:02x}{:02x}".format(*mixed)


def _theme_palette(theme: Dict[str, Any]) -> Dict[str, str]:
    accent = str(theme.get("accent_color") or "#2563eb")
    title = str(theme.get("title_color") or "#0f172a")
    body = str(theme.get("body_color") or "#334155")
    muted = str(theme.get("muted_color") or "#64748b")
    surface = str(theme.get("surface_background") or "#ffffff")
    page = str(theme.get("page_background") or "#ffffff")
    return {
        "series": [
            accent,
            _mix(accent, "#06b6d4", 0.35),
            _mix(accent, "#8b5cf6", 0.35),
            _mix(accent, "#f59e0b", 0.45),
            _mix(accent, "#10b981", 0.35),
        ],
        "text": title,
        "muted_text": muted if muted else body,
        "grid": _mix(muted if muted else body, page, 0.65),
        "value_label": accent,
        "surface": surface,
    }


def _numeric_series(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    series_payload = list(payload.get("series") or [])
    normalized: List[Dict[str, Any]] = []
    for item in series_payload:
        if not isinstance(item, dict):
            continue
        values: List[float] = []
        for raw in list(item.get("values") or []):
            try:
                values.append(float(raw))
            except (TypeError, ValueError):
                continue
        if values:
            normalized.append(
                {
                    "name": str(item.get("name") or f"Series {len(normalized) + 1}").strip(),
                    "values": values,
                }
            )
    return normalized


def _categories(payload: Dict[str, Any], fallback_len: int) -> List[str]:
    categories = [str(item).strip() for item in list(payload.get("categories") or []) if str(item).strip()]
    if categories:
        return categories
    return [f"P{idx + 1}" for idx in range(max(1, fallback_len))]


def _value_label(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return str(round(value, 1))


def _svg_root(*, width: int, height: int, inner: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" '
        f'viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet">{inner}</svg>'
    )


def _render_line_chart(payload: Dict[str, Any], theme: Dict[str, Any], *, width: int, height: int) -> str:
    palette = _theme_palette(theme)
    series = _numeric_series(payload)
    if not series:
        series = [{"name": "Series", "values": [42.0, 55.0, 68.0, 79.0]}]
    categories = _categories(payload, max(len(item["values"]) for item in series))
    title = str(payload.get("title") or "").strip()

    left, right, top, bottom = 52, 24, 56, 48
    plot_w = max(160, width - left - right)
    plot_h = max(110, height - top - bottom)
    all_values = [value for item in series for value in item["values"]] or [0.0]
    max_value = max(all_values)
    min_value = min(all_values)
    if max_value == min_value:
        max_value += 1.0
    spread = max_value - min_value
    x_gap = plot_w / max(1, len(categories) - 1)

    grid = "".join(
        f'<line x1="{left}" y1="{top + plot_h * step / 4:.1f}" x2="{left + plot_w}" y2="{top + plot_h * step / 4:.1f}" '
        f'stroke="{_rgba(palette["grid"], 0.40)}" stroke-width="1"/>'
        for step in range(5)
    )
    labels = "".join(
        f'<text x="{left + idx * x_gap:.1f}" y="{height - 14:.1f}" text-anchor="middle" '
        f'font-size="11" fill="{palette["muted_text"]}">{html.escape(category)}</text>'
        for idx, category in enumerate(categories)
    )
    title_block = (
        f'<text x="{width / 2:.1f}" y="28" text-anchor="middle" font-size="14" font-weight="700" fill="{palette["text"]}">{html.escape(title)}</text>'
        if title
        else ""
    )

    lines: List[str] = []
    series_colors = list(palette["series"])
    for idx, item in enumerate(series):
        color = series_colors[idx % len(series_colors)]
        points = []
        for point_idx, value in enumerate(item["values"]):
            x = left + point_idx * x_gap
            y = top + plot_h - ((value - min_value) / spread) * plot_h
            points.append((x, y, value))
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in points)
        point_marks = "".join(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.8" fill="{color}" stroke="#ffffff" stroke-width="1.5"/>'
            for x, y, _ in points
        )
        last_x, last_y, last_value = points[-1]
        lines.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" points="{poly}"/>'
            f"{point_marks}"
            f'<text x="{last_x + 8:.1f}" y="{last_y - 6:.1f}" font-size="11" font-weight="700" fill="{color}">{html.escape(_value_label(last_value))}</text>'
        )

    return _svg_root(
        width=width,
        height=height,
        inner=(
            f'<rect x="0" y="0" width="{width}" height="{height}" rx="16" fill="{palette["surface"]}"/>'
            f"{title_block}{grid}{labels}{''.join(lines)}"
        ),
    )


def _render_bar_chart(payload: Dict[str, Any], theme: Dict[str, Any], *, width: int, height: int) -> str:
    palette = _theme_palette(theme)
    series = _numeric_series(payload)
    if not series:
        series = [{"name": "Series", "values": [52.0, 47.0, 44.0, 39.0]}]
    categories = _categories(payload, max(len(item["values"]) for item in series))
    title = str(payload.get("title") or "").strip()

    left, right, top, bottom = 48, 20, 54, 52
    plot_w = max(160, width - left - right)
    plot_h = max(110, height - top - bottom)
    all_values = [value for item in series for value in item["values"]] or [0.0]
    max_value = max(all_values) or 1.0

    group_count = max(1, len(categories))
    series_count = max(1, len(series))
    group_width = plot_w / group_count
    bar_gap = max(4.0, group_width * 0.08)
    bar_width = min(30.0, max(10.0, (group_width - bar_gap * (series_count + 1)) / series_count))

    bars: List[str] = []
    series_colors = list(palette["series"])
    for series_idx, item in enumerate(series):
        color = series_colors[series_idx % len(series_colors)]
        for idx, value in enumerate(item["values"]):
            x = left + idx * group_width + bar_gap + series_idx * (bar_width + bar_gap * 0.35)
            bar_h = plot_h * (value / max_value)
            y = top + plot_h - bar_h
            bars.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{bar_h:.1f}" rx="8" fill="{color}"/>'
                f'<text x="{x + bar_width/2:.1f}" y="{y - 6:.1f}" text-anchor="middle" font-size="10.5" font-weight="700" fill="{color}">{html.escape(_value_label(value))}</text>'
            )

    labels = "".join(
        f'<text x="{left + idx * group_width + group_width/2:.1f}" y="{height - 16:.1f}" text-anchor="middle" font-size="11" fill="{palette["muted_text"]}">{html.escape(category)}</text>'
        for idx, category in enumerate(categories)
    )
    title_block = (
        f'<text x="{width / 2:.1f}" y="28" text-anchor="middle" font-size="14" font-weight="700" fill="{palette["text"]}">{html.escape(title)}</text>'
        if title
        else ""
    )

    return _svg_root(
        width=width,
        height=height,
        inner=(
            f'<rect x="0" y="0" width="{width}" height="{height}" rx="16" fill="{palette["surface"]}"/>'
            f"{title_block}{labels}{''.join(bars)}"
        ),
    )


def _render_pie_chart(payload: Dict[str, Any], theme: Dict[str, Any], *, width: int, height: int) -> str:
    import math

    palette = _theme_palette(theme)
    title = str(payload.get("title") or "").strip()
    categories = [str(item).strip() for item in list(payload.get("categories") or []) if str(item).strip()]
    values: List[float] = []
    for raw in list(payload.get("values") or []):
        try:
            values.append(float(raw))
        except Exception:
            continue
    if not values:
        series = _numeric_series(payload)
        if series:
            values = list(series[0].get("values") or [])
            if not categories:
                categories = _categories(payload, len(values))
    if not values:
        values = [40.0, 30.0, 20.0, 10.0]
    if not categories:
        categories = _categories(payload, len(values))
    if len(categories) < len(values):
        categories.extend([f"S{idx + 1}" for idx in range(len(categories), len(values))])

    total = sum(max(0.0, v) for v in values) or 1.0
    cx = int(width * 0.32)
    cy = int(height * 0.56)
    r = int(min(width, height) * 0.22)
    inner_r = int(r * 0.55)
    colors = palette["series"]

    angle = -math.pi / 2
    slices: List[str] = []
    legend: List[str] = []
    for idx, value in enumerate(values):
        ratio = max(0.0, float(value)) / total
        sweep = max(0.001, ratio * 2 * math.pi)
        end = angle + sweep
        color = colors[idx % len(colors)]
        large = 1 if sweep > math.pi else 0

        # Outer arc start/end points
        ox1 = cx + r * math.cos(angle)
        oy1 = cy + r * math.sin(angle)
        ox2 = cx + r * math.cos(end)
        oy2 = cy + r * math.sin(end)
        # Inner arc start/end points (reversed direction)
        ix1 = cx + inner_r * math.cos(end)
        iy1 = cy + inner_r * math.sin(end)
        ix2 = cx + inner_r * math.cos(angle)
        iy2 = cy + inner_r * math.sin(angle)

        # Path: outer arc CW → line to inner → inner arc CCW → close
        d = (
            f"M {ox1:.2f} {oy1:.2f} "
            f"A {r:.2f} {r:.2f} 0 {large} 1 {ox2:.2f} {oy2:.2f} "
            f"L {ix1:.2f} {iy1:.2f} "
            f"A {inner_r:.2f} {inner_r:.2f} 0 {large} 0 {ix2:.2f} {iy2:.2f} "
            f"Z"
        )
        slices.append(f'<path d="{d}" fill="{color}"/>')
        legend_y = 58 + idx * 26
        label = html.escape(categories[idx])
        pct = html.escape(f"{int(round(ratio * 100))}%")
        legend.append(
            f'<rect x="{int(width * 0.58)}" y="{legend_y - 10}" width="12" height="12" rx="4" fill="{color}"/>'
            f'<text x="{int(width * 0.58) + 18}" y="{legend_y}" font-size="11.5" fill="{palette["text"]}">{label}</text>'
            f'<text x="{width - 18}" y="{legend_y}" text-anchor="end" font-size="11.5" font-weight="700" fill="{palette["muted_text"]}">{pct}</text>'
        )
        angle = end

    title_block = (
        f'<text x="{width / 2:.1f}" y="28" text-anchor="middle" font-size="14" font-weight="700" fill="{palette["text"]}">{html.escape(title)}</text>'
        if title
        else ""
    )

    return _svg_root(
        width=width,
        height=height,
        inner=(
            f'<rect x="0" y="0" width="{width}" height="{height}" rx="16" fill="{palette["surface"]}"/>'
            f"{title_block}{''.join(slices)}{''.join(legend)}"
        ),
    )


def render_chart_svg(
    *,
    chart_type: str,
    payload: Dict[str, Any],
    theme: Dict[str, Any],
    width: int = 640,
    height: int = 360,
) -> str:
    ctype = str(chart_type or "").strip().lower()
    if ctype == "line":
        return _render_line_chart(payload=payload, theme=theme, width=width, height=height)
    if ctype == "bar":
        return _render_bar_chart(payload=payload, theme=theme, width=width, height=height)
    if ctype == "pie":
        return _render_pie_chart(payload=payload, theme=theme, width=width, height=height)
    return ""

