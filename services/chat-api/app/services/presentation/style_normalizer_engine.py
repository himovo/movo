from __future__ import annotations

import re
from typing import Any, Dict

from app.services.presentation.contracts import DesignTokens


class StyleNormalizerEngine:
    _ALLOWED_STYLE_KEYS = {
        "background",
        "background_color",
        "border_color",
        "border_width",
        "border_radius",
        "border",
        "border_left",
        "border_right",
        "border_top",
        "border_bottom",
        "color",
        "font_family",
        "font_size",
        "font_weight",
        "font_style",
        "line_height",
        "text_align",
        "vertical_align",
        "box_shadow",
        "opacity",
        "letter_spacing",
        "padding",
        "z_index",
        "line_weight",
        "stroke_dasharray",
        "line_cap",
        "white_space",
        "route",
        "rotation",
    }

    _SHADOW_PRESETS = {
        "soft": "soft",
        "subtle": "subtle",
        "medium": "medium",
        "strong": "strong",
        "none": "none",
    }

    _FONT_WEIGHT_PRESETS = {
        "thin": 100,
        "extralight": 200,
        "ultralight": 200,
        "light": 300,
        "normal": 400,
        "regular": 400,
        "medium": 500,
        "semibold": 600,
        "demibold": 600,
        "bold": 700,
        "extrabold": 800,
        "ultrabold": 800,
        "black": 900,
        "heavy": 900,
    }

    def normalize_style(self, style: Dict[str, Any], *, shape_type: str, tokens: DesignTokens) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for key, value in dict(style or {}).items():
            normalized_key, normalized_value = self.map_style_entry(key, value, shape_type=shape_type)
            if not normalized_key or normalized_value is None:
                continue
            if normalized_key not in self._ALLOWED_STYLE_KEYS:
                continue
            out[normalized_key] = normalized_value

        if shape_type == "page" and "background" not in out:
            out["background"] = tokens.page_background
        return out

    def map_style_entry(self, key: Any, value: Any, *, shape_type: str) -> tuple[str | None, Any | None]:
        raw_name = str(key or "").strip().replace("-", "_")
        name = re.sub(r"(?<!^)(?=[A-Z])", "_", raw_name).lower()
        if not name:
            return None, None
        if isinstance(value, str) and value.strip().lower() == "none":
            if name in {"border_color", "stroke"}:
                return "border_width", 0
            if name in {"background", "background_color", "fill"}:
                return "background", "transparent"
            return None, None

        alias_map = {
            "fill": "background",
            "background_color": "background",
            "stroke": "color" if shape_type == "line" else "border_color",
            "stroke_width": "line_weight" if shape_type == "line" else "border_width",
            "stroke_opacity": "opacity",
            "line_width": "line_weight",
            "lineweight": "line_weight",
            "radius": "border_radius",
            "align": "text_align",
            "valign": "vertical_align",
            "fontfamily": "font_family",
            "fontsize": "font_size",
            "fontweight": "font_weight",
            "linewidth": "line_weight",
            "boxshadow": "box_shadow",
        }
        normalized = alias_map.get(name, name)
        if normalized == "bold":
            return "font_weight", 700 if bool(value) else None
        if normalized == "shadow":
            token = str(value or "").strip().lower()
            return "box_shadow", self._SHADOW_PRESETS.get(token, token if token else None)
        if normalized == "box_shadow":
            if isinstance(value, str):
                token = str(value or "").strip().lower()
                return "box_shadow", self._SHADOW_PRESETS.get(token, value.strip() or None)
            return "box_shadow", value
        if normalized == "vertical_align":
            mapped = {
                "middle": "center",
                "mid": "center",
                "center": "center",
                "top": "top",
                "bottom": "bottom",
            }.get(str(value or "").strip().lower(), str(value or "").strip().lower())
            return "vertical_align", mapped or None
        if normalized == "font_weight":
            if isinstance(value, (int, float)):
                return "font_weight", max(100, min(900, int(value)))
            mapped = str(value).strip().lower().replace(" ", "")
            if mapped in self._FONT_WEIGHT_PRESETS:
                return "font_weight", self._FONT_WEIGHT_PRESETS[mapped]
            try:
                return "font_weight", max(100, min(900, int(float(mapped))))
            except Exception:
                return "font_weight", None
        if normalized in {"font_size", "border_width", "border_radius", "line_weight", "letter_spacing", "rotation", "opacity"}:
            numeric = self.as_number(value)
            return normalized, numeric if numeric is not None else None
        if normalized == "z_index":
            numeric = self.as_number(value)
            return normalized, int(numeric) if numeric is not None else None
        if normalized == "line_height":
            numeric = self.as_number(value)
            return normalized, numeric if numeric is not None else None
        return normalized, str(value).strip() if isinstance(value, str) else value

    @staticmethod
    def has_visual_style(style: Dict[str, Any]) -> bool:
        visible_keys = {"background", "border_color", "border_width", "box_shadow", "color"}
        return any(key in style and str(style.get(key) or "").strip() not in {"", "transparent", "0"} for key in visible_keys)

    @staticmethod
    def as_number(value: Any) -> float | None:
        try:
            if value in (None, ""):
                return None
            return float(value)
        except Exception:
            return None
