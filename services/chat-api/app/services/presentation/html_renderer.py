from __future__ import annotations

import html
import logging
import re
from typing import Any, Dict, List

from app.services.presentation.contracts import (
    FreeformBlock,
    FreeformDeckBlueprint,
    FreeformPageBlueprint,
    HtmlCompileResult,
)
from app.services.presentation.icon_library import load_inline_svg_map, resolve_icon_name
from app.services.presentation.chart_svg_renderer import render_chart_svg
from app.services.presentation.render_utils import (
    chart_theme_from_deck,
    infer_text_vertical_align,
    render_order as shared_render_order,
    resolve_block_content,
    resolve_chart_spec,
)
from app.services.presentation.style_contract import PresentationStyleContract

logger = logging.getLogger(__name__)


def _clamp01(value: Any, default: float) -> float:
    try:
        result = float(value)
    except Exception:
        result = default
    return max(0.0, min(1.0, result))


def _to_kebab(name: str) -> str:
    value = str(name or "").strip().replace("_", "-")
    return re.sub(r"(?<!^)(?=[A-Z])", "-", value).lower()


def _css_value(prop: str, value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    if prop == "box-shadow" and isinstance(value, str):
        presets = {
            "soft": "0 8px 24px rgba(15, 23, 42, 0.10)",
            "subtle": "0 4px 14px rgba(15, 23, 42, 0.08)",
            "medium": "0 10px 28px rgba(15, 23, 42, 0.14)",
            "strong": "0 16px 40px rgba(15, 23, 42, 0.18)",
            "none": "none",
        }
        return presets.get(str(value).strip().lower(), str(value))
    if prop == "font-weight" and isinstance(value, str):
        presets = {
            "normal": "400",
            "regular": "400",
            "medium": "500",
            "semibold": "600",
            "bold": "700",
        }
        return presets.get(str(value).strip().lower(), str(value))
    if isinstance(value, (int, float)) and prop not in {
        "opacity",
        "z-index",
        "font-weight",
        "flex",
        "order",
        "line-height",
    }:
        return f"{value}px"
    if isinstance(value, (int, float)) and prop == "line-height":
        if float(value) <= 4:
            return str(value)
        return f"{value}px"
    if prop == "vertical-align":
        mapped = {
            "center": "middle",
        }.get(str(value), str(value))
        return mapped
    return str(value)


class HtmlRenderer:
    def _chart_theme(self, deck: FreeformDeckBlueprint) -> Dict[str, Any]:
        return chart_theme_from_deck(deck)

    def _resolve_chart_spec(self, shape: FreeformBlock) -> tuple[str, Dict[str, Any]]:
        return resolve_chart_spec(shape)

    def _render_order(self, shape: FreeformBlock) -> tuple[int, str]:
        return shared_render_order(shape)


    def _css_from_style(self, style: Dict[str, Any] | None) -> List[str]:
        css: List[str] = []
        for key, raw_value in dict(style or {}).items():
            prop = _to_kebab(key)
            value = _css_value(prop, raw_value)
            if value is None:
                continue
            css.append(f"{prop}:{value}")
        return css

    def _merge_style_layers(self, *layers: Dict[str, Any] | None) -> Dict[str, Any]:
        merged: Dict[str, Any] = {}
        for layer in layers:
            merged.update(dict(layer or {}))
        return merged

    def _render_text(self, text: Any) -> str:
        return html.escape(str(text or ""))

    def _render_shape(self, shape: FreeformBlock, deck: FreeformDeckBlueprint, parent_rect: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)) -> str:
        shape_type = str(shape.type or "text_box").strip().lower()
        content = resolve_block_content(shape)

        px, py, pw, ph = parent_rect
        pw = max(pw, 0.0001)
        ph = max(ph, 0.0001)

        coord_space = str(getattr(shape, "coordinate_space", "page") or "page").strip().lower()
        if coord_space == "parent":
            shape_x_page = px + float(shape.x or 0.0) * pw
            shape_y_page = py + float(shape.y or 0.0) * ph
            shape_w_page = float(shape.w or 0.0) * pw
            shape_h_page = float(shape.h or 0.0) * ph
        else:
            shape_x_page = float(shape.x or 0.0)
            shape_y_page = float(shape.y or 0.0)
            shape_w_page = float(shape.w or 0.0)
            shape_h_page = float(shape.h or 0.0)

        local_x = (shape_x_page - px) / pw
        local_y = (shape_y_page - py) / ph
        local_w = shape_w_page / pw
        local_h = shape_h_page / ph

        x = local_x * 100.0
        y = local_y * 100.0
        w = max(0.001, local_w) * 100.0
        h = max(0.001, local_h) * 100.0

        current_rect = (shape_x_page, shape_y_page, shape_w_page, shape_h_page)

        merged = dict(shape.style or {})

        if shape_type in {"text_box", "title", "body"}:
            # Ensure overflow visible so long text isn't clipped
            if "overflow" not in merged:
                merged["overflow"] = "visible"

        # Compute CSS z-index from block z_index or fallback
        render_z, _ = self._render_order(shape)
        css = [
            "position:absolute",
            f"left:{x:.2f}%",
            f"top:{y:.2f}%",
            f"width:{w:.2f}%",
            f"height:{h:.2f}%",
            "box-sizing:border-box",
            f"z-index:{render_z}",
        ]
        
        # If text aligns center, we default flex for text_box to vertical center it if needed,
        # but simple block display is also fine.
        if shape_type == "group":
            css.append("overflow:visible")
        css.extend(self._css_from_style({k: v for k, v in merged.items() if k != "line_weight"}))
        style_attr = ";".join(css)
        
        # Handle Children recursively if group
        sorted_children = sorted(list(shape.children or []), key=self._render_order)
        children_html = "".join([self._render_shape(c, deck, parent_rect=current_rect) for c in sorted_children])
        
        if shape_type == "rectangle":
            return f'<div class="ff-shape-rect" id="{html.escape(shape.id)}" style="{style_attr}">{children_html}</div>'
        elif shape_type == "circle":
            style_attr += ";border-radius:50%"
            circle_text = ""
            if content:
                circle_text = html.escape(content).replace("\\n", "<br/>").replace("\n", "<br/>")
                style_attr += ";display:flex;align-items:center;justify-content:center;text-align:center"
            return f'<div class="ff-shape-circle" id="{html.escape(shape.id)}" style="{style_attr}">{circle_text}{children_html}</div>'
        elif shape_type == "line":
            line_weight = merged.get("line_weight")
            try:
                thickness_px = max(1.0, float(line_weight)) if line_weight not in (None, "") else 1.0
            except Exception:
                thickness_px = 1.0
            color = str(
                merged.get("color")
                or merged.get("background")
                or merged.get("border_color")
                or getattr(deck.theme, "accent_color", "")
                or "#000000"
            ).strip()
            x1 = x
            y1 = y

            if shape.x2 is not None:
                if coord_space == "parent":
                    shape_x2_page = px + float(shape.x2) * pw
                else:
                    shape_x2_page = float(shape.x2)
            else:
                shape_x2_page = shape_x_page

            if shape.y2 is not None:
                if coord_space == "parent":
                    shape_y2_page = py + float(shape.y2) * ph
                else:
                    shape_y2_page = float(shape.y2)
            else:
                shape_y2_page = shape_y_page

            x2 = ((shape_x2_page - px) / pw) * 100.0
            y2 = ((shape_y2_page - py) / ph) * 100.0

            left = min(x1, x2)
            top = min(y1, y2)
            width = max(abs(x2 - x1), 0.10)
            height = max(abs(y2 - y1), 0.10)
            local_x1 = 0.0 if x1 <= x2 else width
            local_x2 = width if x1 <= x2 else 0.0
            local_y1 = 0.0 if y1 <= y2 else height
            local_y2 = height if y1 <= y2 else 0.0
            svg_style = ";".join(
                [
                    "position:absolute",
                    f"left:{left:.2f}%",
                    f"top:{top:.2f}%",
                    f"width:{width:.2f}%",
                    f"height:{height:.2f}%",
                    "overflow:visible",
                    "pointer-events:none",
                    f"z-index:{render_z}",
                ]
            )
            dash = merged.get("stroke_dasharray")
            dash_attr = f' stroke-dasharray="{html.escape(str(dash))}"' if dash not in (None, "") else ""
            opacity = merged.get("opacity")
            opacity_attr = f' opacity="{html.escape(str(opacity))}"' if opacity not in (None, "") else ""
            # Use pixel-based viewBox to avoid stroke distortion from preserveAspectRatio="none"
            vb_w = width / 100.0 * 1600.0  # convert percentage to pixels (1600px canvas)
            vb_h = height / 100.0 * 900.0   # convert percentage to pixels (900px canvas)
            vb_w = max(vb_w, 1.0)
            vb_h = max(vb_h, 1.0)
            lx1 = (local_x1 / max(width, 0.001)) * vb_w
            ly1 = (local_y1 / max(height, 0.001)) * vb_h
            lx2 = (local_x2 / max(width, 0.001)) * vb_w
            ly2 = (local_y2 / max(height, 0.001)) * vb_h
            return (
                f'<svg class="ff-shape-line" id="{html.escape(shape.id)}" style="{svg_style}" '
                f'viewBox="0 0 {vb_w:.2f} {vb_h:.2f}" preserveAspectRatio="none">'
                f'<line x1="{lx1:.2f}" y1="{ly1:.2f}" x2="{lx2:.2f}" y2="{ly2:.2f}" '
                f'stroke="{html.escape(color)}" stroke-width="{thickness_px:.2f}" stroke-linecap="round"{dash_attr}{opacity_attr} '
                f'vector-effect="non-scaling-stroke" />'
                f"</svg>"
            )
        elif shape_type == "image":
            img_src = str(content).strip()
            image_prompt = html.escape(str(shape.image_prompt or "").strip())
            if img_src and not img_src.startswith("{") and (
                img_src.startswith("http")
                or img_src.startswith("/")
                or img_src.startswith("data:image/")
            ):
                # Real image URL
                return f'<img class="ff-shape-image" id="{html.escape(shape.id)}" src="{html.escape(img_src)}" style="{style_attr};object-fit:cover" />'
            else:
                # Placeholder: show image_prompt or content as description
                placeholder_text = image_prompt or html.escape(img_src) or "Image"
                return (
                    f'<div class="ff-shape-image-placeholder" id="{html.escape(shape.id)}" '
                    f'style="{style_attr};background:#e8ecf0;border:2px dashed #b0b8c4;border-radius:8px;'
                    f'display:flex;align-items:center;justify-content:center;flex-direction:column;overflow:hidden">'
                    f'<svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#8896a7" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom:6px">'
                    f'<rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>'
                    f'<circle cx="8.5" cy="8.5" r="1.5"/>'
                    f'<polyline points="21 15 16 10 5 21"/></svg>'
                    f'<span style="font-size:13px;color:#8896a7;text-align:center;padding:0 8px;max-width:90%;word-break:break-word">{placeholder_text}</span>'
                    f'</div>'
                )
        elif shape_type == "chart":
            chart_type, chart_payload = self._resolve_chart_spec(shape)
            chart_w = max(160, int(round(shape_w_page * 1600)))
            chart_h = max(120, int(round(shape_h_page * 900)))
            chart_svg = ""
            if chart_type:
                chart_svg = render_chart_svg(
                    chart_type=chart_type,
                    payload=chart_payload,
                    theme=self._chart_theme(deck),
                    width=chart_w,
                    height=chart_h,
                )
            if chart_svg:
                return (
                    f'<div class="ff-shape-chart" id="{html.escape(shape.id)}" '
                    f'style="{style_attr};overflow:hidden">{chart_svg}</div>'
                )
            fallback = html.escape(str(chart_payload.get("title") or "Chart"))
            return (
                f'<div class="ff-shape-chart-placeholder" id="{html.escape(shape.id)}" '
                f'style="{style_attr};background:#f8fafc;border:1px dashed #94a3b8;border-radius:10px;'
                f'display:flex;align-items:center;justify-content:center;color:#64748b;font-size:14px">{fallback}</div>'
            )
        elif shape_type == "icon":
            # Render inline SVG icon — try pre-resolved svg, fallback to resolving here
            icon_svg = str(shape.icon_svg or "").strip()
            if not icon_svg:
                raw_name = str(shape.icon or shape.content or "").strip()
                if raw_name:
                    resolved = resolve_icon_name(raw_name, fallback="sparkles")
                    svg_map = load_inline_svg_map()
                    icon_svg = str(svg_map.get(resolved) or "").strip()
            icon_color = str(merged.get("color") or getattr(deck.theme, "accent_color", "") or "#000000").strip()
            if icon_svg:
                # Force icon color and make it fill the container
                icon_svg = icon_svg.replace("currentColor", icon_color)
                icon_svg = re.sub(
                    r"<svg\b",
                    '<svg width="100%" height="100%" style="display:block"',
                    icon_svg,
                    count=1,
                )
            else:
                icon_svg = ""
            return (
                f'<div class="ff-shape-icon" id="{html.escape(shape.id)}" '
                f'style="{style_attr};display:flex;align-items:center;justify-content:center;overflow:visible">'
                f'{icon_svg}</div>'
            )
        elif shape_type == "group":
            return f'<div class="ff-shape-group" id="{html.escape(shape.id)}" style="{style_attr}">{children_html}</div>'
        else:
            # text_box
            safe_text = html.escape(content).replace("\\n", "<br/>").replace("\n", "<br/>")
            vertical_align = infer_text_vertical_align(
                content=content,
                style=merged,
                box_height_norm=shape_h_page,
            )
            if vertical_align in {"center", "middle", "bottom", "top"}:
                align_items = {
                    "top": "flex-start",
                    "bottom": "flex-end",
                    "center": "center",
                    "middle": "center",
                }[vertical_align]
                style_attr += f";display:flex;flex-direction:column;justify-content:{align_items}"
            return f'<div class="ff-shape-text" id="{html.escape(shape.id)}" style="{style_attr}">{safe_text}{children_html}</div>'

    def _render_page(self, page: FreeformPageBlueprint, deck: FreeformDeckBlueprint) -> str:
        sorted_blocks = sorted(list(page.blocks or []), key=self._render_order)
        block_html = "".join(self._render_shape(block, deck) for block in sorted_blocks)
        page_style = self._merge_style_layers(deck.theme.page_style, dict(page.style or {}))
        surface_style = self._merge_style_layers(deck.theme.surface_style)
        page_css = ";".join(self._css_from_style(page_style))
        surface_css = ";".join(["position:absolute", "inset:0"] + self._css_from_style(surface_style))
        return (
            f'<section class="ff-page-frame" data-page-id="{html.escape(page.page_id)}">'
            f'<div class="ff-page" style="{html.escape(page_css)}">'
            f'<div class="ff-page-surface" style="{html.escape(surface_css)}">{block_html}</div>'
            "</div>"
            "</section>"
        )

    def compile(self, *, blueprint: FreeformDeckBlueprint) -> HtmlCompileResult:
        blueprint = PresentationStyleContract().canonicalize(blueprint)
        logger.info(
            "presentation_html_compile_start deck_id=%s page_count=%s",
            str(blueprint.deck_id or "").strip(),
            len(list(blueprint.pages or [])),
        )
        pages_html = "".join(self._render_page(page, blueprint) for page in list(blueprint.pages or []))
        document_style = dict(blueprint.theme.document_style or {})
        # Preview canvas background should stay stable and not vary by theme.
        document_style.pop("background", None)
        document_style.pop("background_color", None)
        document_css = ";".join(self._css_from_style(document_style))
        deck_css = ";".join(self._css_from_style(blueprint.theme.deck_style))
        custom_css = str(blueprint.theme.custom_css or "")
        html_text = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html.escape(blueprint.deck_goal or blueprint.deck_id)}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #e5e7eb; }}
    .ff-deck {{ width: 100%; display: flex; flex-direction: column; align-items: center; padding-top: 40px; }}
    :root {{
      --ff-scale: 0.6;
    }}
    .ff-page-frame {{
      width: calc(1600px * var(--ff-scale));
      height: calc(900px * var(--ff-scale));
      margin: 0 auto 40px;
      position: relative;
      border-radius: 6px;
      box-shadow: 0 2px 12px rgba(0, 0, 0, 0.12), 0 0 0 1px rgba(0, 0, 0, 0.06);
      overflow: hidden;
    }}
    .ff-page {{
      width: 1600px;
      height: 900px;
      position: absolute;
      left: 0;
      top: 0;
      overflow: hidden;
      transform-origin: top left;
      transform: scale(var(--ff-scale));
    }}
    .ff-shape-text {{
      word-wrap: break-word;
      white-space: pre-wrap;
      overflow: visible;
    }}
    {custom_css}
  </style>
</head>
<body style="{html.escape(document_css)}">
  <main class="ff-deck" style="{html.escape(deck_css)}">{pages_html}</main>
  <script>
    (function() {{
      function updateScale() {{
        var viewportWidth = window.innerWidth || document.documentElement.clientWidth || 1600;
        var scale = Math.min((viewportWidth - 64) / 1600, 1);
        if (!isFinite(scale) || scale <= 0) {{
          scale = 0.6;
        }}
        document.documentElement.style.setProperty('--ff-scale', String(scale));
      }}
      updateScale();
      window.addEventListener('resize', updateScale);
    }})();
  </script>
</body>
</html>"""
        result = HtmlCompileResult(
            html=html_text,
            slide_count=len(list(blueprint.pages or [])),
            metadata={
                "pipeline_version": "current",
                "render_mode": "freeform_blueprint_html",
            },
        )
        logger.info(
            "presentation_html_compile_done deck_id=%s slide_count=%s html_chars=%s",
            str(blueprint.deck_id or "").strip(),
            int(result.slide_count or 0),
            len(result.html),
        )
        return result
