from __future__ import annotations

from typing import Any, Dict

from app.services.presentation.contracts import (
    DesignTokens,
    FreeformBlock,
    FreeformDeckBlueprint,
)
from app.services.presentation.style_normalizer_engine import StyleNormalizerEngine
from app.services.presentation.typography_policy import PresentationTypographyPolicy
from app.services.presentation.icon_library import resolve_icon_from_texts
from app.services.presentation.text_fit_policy import fit_text_style_to_box


class PresentationStyleContract:
    """Canonical style boundary shared by preview, editor, and PPTX export.

    LLMs commonly mix CSS camelCase, SVG names, and the blueprint's snake_case
    style vocabulary.  This adapter converts those aliases once without changing
    geometry or introducing a visual template.
    """

    VERSION = "2026-08-31"

    def __init__(self) -> None:
        self._normalizer = StyleNormalizerEngine()
        self._typography = PresentationTypographyPolicy()

    def canonicalize(self, blueprint: FreeformDeckBlueprint) -> FreeformDeckBlueprint:
        out = blueprint.model_copy(deep=True)
        tokens = self._tokens(out)
        out.theme.document_style = self._normalize_style(out.theme.document_style, "document", tokens)
        out.theme.deck_style = self._normalize_style(out.theme.deck_style, "deck", tokens)
        out.theme.page_style = self._normalize_style(out.theme.page_style, "page", tokens)
        out.theme.surface_style = self._normalize_style(out.theme.surface_style, "surface", tokens)
        out.theme.role_styles = {
            str(role): self._normalize_style(style, "text_box", tokens)
            for role, style in dict(out.theme.role_styles or {}).items()
        }
        for page in list(out.pages or []):
            page.style = self._normalize_style(page.style, "page", tokens)
            page.blocks = [
                self._canonicalize_block(block, tokens, out.theme.role_styles, (1.0, 1.0))
                for block in list(page.blocks or [])
            ]
        out.runtime = dict(out.runtime or {})
        out.runtime["style_contract_version"] = self.VERSION
        return out

    def _canonicalize_block(
        self,
        block: FreeformBlock,
        tokens: DesignTokens,
        role_styles: Dict[str, Dict[str, Any]],
        parent_size: tuple[float, float],
    ) -> FreeformBlock:
        item = block.model_copy(deep=True)
        shape_type = str(item.type or "text_box").strip().lower()
        role = str(item.role or "").strip().lower()
        if str(item.coordinate_space or "page").strip().lower() == "parent":
            actual_w = float(item.w or 0.0) * max(0.0001, parent_size[0])
            actual_h = float(item.h or 0.0) * max(0.0001, parent_size[1])
        else:
            actual_w = float(item.w or 0.0)
            actual_h = float(item.h or 0.0)
        inherited = self._role_style(role=role, shape_type=shape_type, role_styles=role_styles)
        item.style = self._normalize_style({**inherited, **dict(item.style or {})}, shape_type, tokens)
        self._apply_readability_defaults(item, tokens)
        if shape_type == "text_box":
            item.style = self._typography.apply(role=role, style=item.style)
            item.style = fit_text_style_to_box(
                content=str(item.content or ""),
                box_w=actual_w,
                box_h=actual_h,
                style=item.style,
                floor=float(self._typography.minimum_size(role)),
            )
        elif shape_type == "icon":
            item.icon = resolve_icon_from_texts(item.icon, role, item.content, fallback="bulb")
        item.children = [
            self._canonicalize_block(child, tokens, role_styles, (actual_w, actual_h))
            for child in list(item.children or [])
        ]
        return item

    @staticmethod
    def _role_style(
        *, role: str, shape_type: str, role_styles: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        if shape_type != "text_box":
            return {}
        exact = dict(role_styles.get(role) or {})
        if exact:
            return exact
        if role in {"hero_title", "main_title", "cover_title", "headline", "headline_claim", "takeaway"}:
            return dict(role_styles.get("title") or role_styles.get("headline") or {})
        if role in {"subtitle", "section_title", "subheading", "section_label", "phase_label"}:
            return dict(role_styles.get("subtitle") or {})
        if role in {"label", "tag", "meta", "eyebrow", "caption", "annotation", "footnote", "source"}:
            return dict(role_styles.get("label") or role_styles.get("body") or {})
        return dict(role_styles.get("body") or {})

    def _normalize_style(self, style: Dict[str, Any], shape_type: str, tokens: DesignTokens) -> Dict[str, Any]:
        return self._normalizer.normalize_style(dict(style or {}), shape_type=shape_type, tokens=tokens)

    @staticmethod
    def _tokens(blueprint: FreeformDeckBlueprint) -> DesignTokens:
        theme = blueprint.theme
        title_style = dict(theme.role_styles.get("title") or theme.role_styles.get("headline") or {})
        body_style = dict(theme.role_styles.get("body") or {})
        return DesignTokens(
            primary_color=str(theme.accent_color or "#2563eb"),
            secondary_color=str(theme.title_color or "#0f172a"),
            accent_color=str(theme.accent_color or "#38bdf8"),
            page_background=str(theme.page_style.get("background") or theme.page_background or "#ffffff"),
            title_color=str(title_style.get("color") or theme.title_color or "#111111"),
            body_color=str(body_style.get("color") or theme.body_color or "#222222"),
            muted_color=str(theme.muted_color or "#666666"),
            title_font_size=int(title_style.get("font_size") or 48),
            body_font_size=int(body_style.get("font_size") or 22),
            font_family=str(theme.font_family or "'PingFang SC', 'Microsoft YaHei', sans-serif"),
        )

    @staticmethod
    def _apply_readability_defaults(block: FreeformBlock, tokens: DesignTokens) -> None:
        style = block.style
        shape_type = str(block.type or "text_box").strip().lower()
        role = str(block.role or "").strip().lower()
        if shape_type == "text_box":
            is_title = role in {"title", "headline", "hero_title", "main_title"}
            is_subtitle = role in {"subtitle", "section_title", "subheading"}
            style.setdefault("font_family", tokens.font_family)
            style.setdefault("font_size", tokens.title_font_size if is_title else (tokens.subtitle_font_size if is_subtitle else max(16, tokens.body_font_size)))
            style.setdefault("font_weight", 700 if is_title else (600 if is_subtitle else 400))
            style.setdefault("color", tokens.title_color if is_title or is_subtitle else tokens.body_color)
            style.setdefault("text_align", "left")
        elif shape_type == "line":
            style.setdefault("color", tokens.secondary_color)
            style.setdefault("line_weight", max(1, tokens.line_weight))
        elif shape_type == "icon":
            style.setdefault("color", tokens.primary_color)


__all__ = ["PresentationStyleContract"]
