from __future__ import annotations

import re
from typing import Dict, List

from app.services.presentation.contracts import DesignTokens, FreeformTheme


ThemeSpec = Dict[str, object]


THEME_FACTORY_SPECS: List[ThemeSpec] = [
    {
        "slug": "ocean-depths",
        "name": "Ocean Depths",
        "colors": {
            "primary": "#1a2332",
            "secondary": "#2d8b8b",
            "accent": "#a8dadc",
            "background": "#f1faee",
        },
        "typography": {"header": "DejaVu Sans Bold", "body": "DejaVu Sans"},
        "best_for": "Corporate presentations, financial reports, consulting decks.",
    },
    {
        "slug": "sunset-boulevard",
        "name": "Sunset Boulevard",
        "colors": {
            "primary": "#e76f51",
            "secondary": "#f4a261",
            "accent": "#e9c46a",
            "background": "#fff6ed",
        },
        "typography": {"header": "DejaVu Serif Bold", "body": "DejaVu Sans"},
        "best_for": "Creative pitches, marketing, lifestyle and events.",
    },
    {
        "slug": "forest-canopy",
        "name": "Forest Canopy",
        "colors": {
            "primary": "#2d4a2b",
            "secondary": "#7d8471",
            "accent": "#a4ac86",
            "background": "#faf9f6",
        },
        "typography": {"header": "FreeSerif Bold", "body": "FreeSans"},
        "best_for": "Sustainability, outdoor and wellness topics.",
    },
    {
        "slug": "modern-minimalist",
        "name": "Modern Minimalist",
        "colors": {
            "primary": "#36454f",
            "secondary": "#708090",
            "accent": "#d3d3d3",
            "background": "#ffffff",
        },
        "typography": {"header": "DejaVu Sans Bold", "body": "DejaVu Sans"},
        "best_for": "Tech, architecture, design and data-heavy decks.",
    },
    {
        "slug": "golden-hour",
        "name": "Golden Hour",
        "colors": {
            "primary": "#f4a900",
            "secondary": "#c1666b",
            "accent": "#d4b896",
            "background": "#fff8ef",
        },
        "typography": {"header": "FreeSans Bold", "body": "FreeSans"},
        "best_for": "Hospitality, dining, artisan and lifestyle brands.",
    },
    {
        "slug": "arctic-frost",
        "name": "Arctic Frost",
        "colors": {
            "primary": "#4a6fa5",
            "secondary": "#c0c0c0",
            "accent": "#d4e4f7",
            "background": "#fafafa",
        },
        "typography": {"header": "DejaVu Sans Bold", "body": "DejaVu Sans"},
        "best_for": "Healthcare, technology and pharmaceutical content.",
    },
    {
        "slug": "desert-rose",
        "name": "Desert Rose",
        "colors": {
            "primary": "#b87d6d",
            "secondary": "#5d2e46",
            "accent": "#d4a5a5",
            "background": "#e8d5c4",
        },
        "typography": {"header": "FreeSans Bold", "body": "FreeSans"},
        "best_for": "Fashion, beauty, wedding and interior design topics.",
    },
    {
        "slug": "tech-innovation",
        "name": "Tech Innovation",
        "colors": {
            "primary": "#0066ff",
            "secondary": "#1e1e1e",
            "accent": "#22d3ee",
            "background": "#ffffff",
        },
        "typography": {"header": "DejaVu Sans Bold", "body": "DejaVu Sans"},
        "best_for": "Startups, software launches, AI and innovation decks.",
    },
    {
        "slug": "botanical-garden",
        "name": "Botanical Garden",
        "colors": {
            "primary": "#4a7c59",
            "secondary": "#b7472a",
            "accent": "#f9a620",
            "background": "#f5f3ed",
        },
        "typography": {"header": "DejaVu Serif Bold", "body": "DejaVu Sans"},
        "best_for": "Food, natural products and farm-to-table stories.",
    },
    {
        "slug": "midnight-galaxy",
        "name": "Midnight Galaxy",
        "colors": {
            "primary": "#2b1e3e",
            "secondary": "#4a4e8f",
            "accent": "#a490c2",
            "background": "#f7f5ff",
        },
        "typography": {"header": "FreeSans Bold", "body": "FreeSans"},
        "best_for": "Entertainment, gaming, nightlife and creative agencies.",
    },
]


def theme_catalog_prompt_text() -> str:
    lines: List[str] = []
    for item in THEME_FACTORY_SPECS:
        colors = item.get("colors") if isinstance(item.get("colors"), dict) else {}
        lines.append(
            (
                f"- {item.get('slug')}: {item.get('name')} | "
                f"primary={colors.get('primary')} secondary={colors.get('secondary')} "
                f"accent={colors.get('accent')} background={colors.get('background')} | "
                f"best_for={item.get('best_for')}"
            )
        )
    return "\n".join(lines)


def get_theme_spec_by_slug(slug: str) -> ThemeSpec | None:
    normalized = str(slug or "").strip().lower()
    normalized_spaced = normalized.replace("-", " ").replace("_", " ")
    for item in THEME_FACTORY_SPECS:
        item_slug = str(item.get("slug") or "").strip().lower()
        item_name = str(item.get("name") or "").strip().lower()
        if item_slug == normalized or item_name == normalized or item_name == normalized_spaced:
            return item
    return None


def apply_theme_spec_to_design_tokens(tokens: DesignTokens, theme_spec: ThemeSpec | None) -> DesignTokens:
    if not theme_spec:
        return tokens
    colors = theme_spec.get("colors") if isinstance(theme_spec.get("colors"), dict) else {}
    primary = str(colors.get("primary") or tokens.primary_color).strip() or tokens.primary_color
    secondary = str(colors.get("secondary") or tokens.secondary_color).strip() or tokens.secondary_color
    accent = str(colors.get("accent") or tokens.accent_color).strip() or tokens.accent_color
    background = str(colors.get("background") or tokens.page_background).strip() or tokens.page_background
    updated = tokens.model_copy(deep=True)
    updated.primary_color = primary
    updated.secondary_color = secondary
    updated.accent_color = accent
    updated.page_background = background
    updated.surface_background = _derive_surface_background(background=background, accent=accent)
    updated.title_color = secondary if secondary.startswith("#") else tokens.title_color
    updated.body_color = "#1f2937"
    updated.muted_color = "#6b7280"
    updated.shadow_style = "soft"
    # Keep Chinese-first default for rendering reliability.
    updated.font_family = "Microsoft YaHei"
    return updated


def infer_theme_spec(
    *,
    deck_goal: str,
    target_audience: str,
    user_outline: str,
) -> ThemeSpec:
    signal = " ".join(
        [
            str(deck_goal or "").lower(),
            str(target_audience or "").lower(),
            str(user_outline or "").lower(),
        ]
    )
    by_keywords = [
        (("tech", "ai", "software", "创新", "智能", "大模型"), "tech-innovation"),
        (("health", "medical", "pharma", "医疗"), "arctic-frost"),
        (("finance", "consulting", "corporate", "财务", "咨询"), "ocean-depths"),
        (("fashion", "beauty", "wedding", "时尚", "美妆"), "desert-rose"),
        (("food", "hospitality", "dining", "餐饮"), "golden-hour"),
        (("sustainability", "green", "outdoor", "可持续"), "forest-canopy"),
        (("creative", "marketing", "lifestyle", "品牌", "市场"), "sunset-boulevard"),
    ]
    for keywords, slug in by_keywords:
        if any(token in signal for token in keywords):
            found = get_theme_spec_by_slug(slug)
            if found:
                return found
    fallback = get_theme_spec_by_slug("modern-minimalist")
    return fallback if fallback else dict(THEME_FACTORY_SPECS[0])


def build_freeform_theme_from_design_tokens(tokens: DesignTokens) -> FreeformTheme:
    page_bg = str(tokens.page_background or "#ffffff").strip() or "#ffffff"
    title_color = str(tokens.title_color or "#111111").strip() or "#111111"
    body_color = str(tokens.body_color or "#222222").strip() or "#222222"
    muted_color = str(tokens.muted_color or "#666666").strip() or "#666666"
    accent = str(tokens.accent_color or tokens.primary_color or "#2563eb").strip() or "#2563eb"

    theme = FreeformTheme(
        page_background=page_bg,
        surface_background="transparent",
        accent_color=accent,
        title_color=title_color,
        body_color=body_color,
        muted_color=muted_color,
        font_family=str(tokens.font_family or "Microsoft YaHei").strip() or "Microsoft YaHei",
        surface_shadow=str(tokens.shadow_style or "subtle").strip() or "subtle",
    )
    theme.document_style = {"background": page_bg}
    theme.page_style = {"background": page_bg}
    # The slide surface is a canvas, not a compulsory full-page card.
    theme.surface_style = {"background": "transparent"}
    theme.role_styles = {
        "title": {"color": title_color, "font_weight": 700},
        "subtitle": {"color": muted_color},
        "body": {"color": body_color},
        "label": {"color": body_color},
    }
    return theme


def _derive_surface_background(*, background: str, accent: str) -> str:
    bg = _parse_hex(background)
    if bg is None:
        return "#f8fafc"
    # Use a neutral tint (light gray) instead of mixing accent color,
    # which can produce unwanted colored surfaces (e.g. cyan tint on every page).
    neutral_gray = (245, 245, 245)  # #f5f5f5
    bg_luma = _relative_luminance(*bg)
    if bg_luma >= 0.78:
        # Light background: use a very subtle gray to add depth
        return "#f5f5f5"
    else:
        # Dark background: lighten slightly
        mixed = _mix(bg, neutral_gray, 0.06)
        return "#%02x%02x%02x" % mixed


def _parse_hex(value: str) -> tuple[int, int, int] | None:
    token = str(value or "").strip()
    if not token:
        return None
    if token.startswith("#"):
        raw = token[1:]
        if len(raw) == 3:
            raw = "".join(ch * 2 for ch in raw)
        if len(raw) == 6 and re.fullmatch(r"[0-9a-fA-F]{6}", raw):
            return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
        return None
    return None


def _mix(bg: tuple[int, int, int], fg: tuple[int, int, int], alpha: float) -> tuple[int, int, int]:
    a = max(0.0, min(1.0, float(alpha)))
    return (
        int(round(bg[0] * (1.0 - a) + fg[0] * a)),
        int(round(bg[1] * (1.0 - a) + fg[1] * a)),
        int(round(bg[2] * (1.0 - a) + fg[2] * a)),
    )


def _relative_luminance(r: int, g: int, b: int) -> float:
    def channel(v: int) -> float:
        s = v / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
