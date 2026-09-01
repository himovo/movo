from __future__ import annotations

import json
import logging
import uuid
from io import BytesIO
from typing import Any, Dict, List, Optional
from PIL import Image

from app.services.presentation.contracts import (
    FreeformBlock,
    FreeformDeckBlueprint,
    FreeformPageBlueprint,
)
from app.services.image_generation import generate_image
from app.utils.oss_uploader import AliyunOSSUploader

logger = logging.getLogger(__name__)


class CoverImageComposer:
    """Programmatic cover enhancer.

    Behavior:
    - Always attempts to generate a no-text cover background via gpt-image-2.
    - Preserves the LLM-authored cover composition and injects the image behind it.
    - If generation fails for any reason, keeps the original cover unchanged.
    """

    def __init__(self, *, timeout_seconds: float = 80.0) -> None:
        self._timeout_seconds = float(timeout_seconds)

    async def compose(
        self,
        *,
        blueprint: FreeformDeckBlueprint,
        user_id: str,
        preserve_layout: bool = True,
    ) -> FreeformDeckBlueprint:
        cover_idx = self._find_cover_index(blueprint)
        if cover_idx < 0:
            logger.info("presentation_cover_compose skipped reason=no_cover_page deck_id=%s", str(blueprint.deck_id or "").strip())
            return blueprint

        page = list(blueprint.pages or [])[cover_idx]
        deck_runtime = dict(blueprint.runtime or {})
        cover_brief = self._find_cover_brief(page=page, deck_runtime=deck_runtime)
        texts = self._extract_cover_texts(page=page, deck_runtime=deck_runtime, cover_brief=cover_brief)
        if not texts.get("title"):
            logger.warning(
                "presentation_cover_compose skipped reason=empty_cover_title deck_id=%s page_id=%s",
                str(blueprint.deck_id or "").strip(),
                str(page.page_id or "").strip(),
            )
            return blueprint

        prompt = self._build_cover_prompt(
            blueprint=blueprint,
            texts=texts,
            cover_brief=cover_brief,
        )
        logger.info(
            "presentation_cover_compose start deck_id=%s page_id=%s",
            str(blueprint.deck_id or "").strip(),
            str(page.page_id or "").strip(),
        )
        generated = await self._generate_cover_background(prompt=prompt, user_id=user_id)
        if not generated:
            logger.warning(
                "presentation_cover_compose fallback reason=image_generation_failed deck_id=%s page_id=%s",
                str(blueprint.deck_id or "").strip(),
                str(page.page_id or "").strip(),
            )
            return blueprint

        updated = blueprint.model_copy(deep=True)
        pages = list(updated.pages or [])
        if preserve_layout:
            pages[cover_idx] = self._inject_background_image(pages[cover_idx], generated)
        else:
            pages[cover_idx] = self._rebuild_cover_page(
                page=pages[cover_idx],
                image_url=generated,
                texts=texts,
                theme=updated.theme.model_dump(),
                deck_runtime=deck_runtime,
            )
        updated.pages = pages
        logger.info(
            "presentation_cover_compose done deck_id=%s page_id=%s",
            str(updated.deck_id or "").strip(),
            str(pages[cover_idx].page_id or "").strip(),
        )
        return updated

    def _inject_background_image(
        self, page: FreeformPageBlueprint, image_url: str
    ) -> FreeformPageBlueprint:
        """Add a generated hero image without replacing authored geometry."""
        updated = page.model_copy(deep=True)
        retained: List[FreeformBlock] = []
        for block in list(updated.blocks or []):
            role = str(block.role or "").strip().lower()
            is_old_generated_background = (
                role == "background"
                and float(block.w or 0.0) >= 0.95
                and float(block.h or 0.0) >= 0.95
            )
            if not is_old_generated_background:
                retained.append(block)
        background = FreeformBlock(
            id=f"{updated.page_id}_generated_cover_background",
            type="image",
            role="background",
            x=0.0,
            y=0.0,
            w=1.0,
            h=1.0,
            z_index=0,
            content=image_url,
            style={"fit": "cover"},
        )
        updated.blocks = [background, *retained]
        return updated

    def _find_cover_index(self, blueprint: FreeformDeckBlueprint) -> int:
        pages = list(blueprint.pages or [])
        if not pages:
            return -1
        runtime = dict(blueprint.runtime or {})
        deck_brief = runtime.get("deck_brief") if isinstance(runtime.get("deck_brief"), dict) else {}
        briefs = list(deck_brief.get("page_briefs") or []) if isinstance(deck_brief, dict) else []
        cover_page_id = ""
        for brief in briefs:
            if not isinstance(brief, dict):
                continue
            if str(brief.get("page_type") or "").strip().lower() == "cover":
                cover_page_id = str(brief.get("page_id") or "").strip()
                if cover_page_id:
                    break
        if cover_page_id:
            for idx, page in enumerate(pages):
                if str(page.page_id or "").strip() == cover_page_id:
                    return idx
        return 0

    def _find_cover_brief(self, *, page: FreeformPageBlueprint, deck_runtime: Dict[str, Any]) -> Dict[str, Any]:
        deck_brief = deck_runtime.get("deck_brief") if isinstance(deck_runtime.get("deck_brief"), dict) else {}
        for brief in list(deck_brief.get("page_briefs") or []):
            if not isinstance(brief, dict):
                continue
            if str(brief.get("page_id") or "").strip() == str(page.page_id or "").strip():
                return dict(brief)
        return {}

    def _extract_cover_texts(
        self,
        *,
        page: FreeformPageBlueprint,
        deck_runtime: Dict[str, Any],
        cover_brief: Dict[str, Any],
    ) -> Dict[str, str]:
        visible = self._extract_visible_cover_copy_from_page(page)
        explicit = self._extract_cover_copy_from_brief(cover_brief)
        if visible.get("title"):
            return {
                "title": str(visible.get("title") or "").strip(),
                "subtitle": str(visible.get("subtitle") or explicit.get("subtitle") or "").strip(),
                "tag": str(
                    visible.get("tag")
                    or explicit.get("tag")
                    or self._default_presenter_tag(deck_runtime)
                ).strip(),
            }
        if explicit.get("title"):
            if not str(explicit.get("tag") or "").strip():
                explicit["tag"] = self._default_presenter_tag(deck_runtime)
            return explicit
        return self._fallback_cover_copy(deck_runtime=deck_runtime, page=page, cover_brief=cover_brief)

    def _extract_visible_cover_copy_from_page(self, page: FreeformPageBlueprint) -> Dict[str, str]:
        def _item_text(item: Any) -> str:
            if not isinstance(item, dict):
                return ""
            return str(item.get("text") or "").strip()

        candidates: List[Dict[str, Any]] = []
        for block in list(page.blocks or []):
            self._walk_cover_text_candidates(block, candidates)
        if not candidates:
            return {}

        title_candidates = [item for item in candidates if self._is_title_candidate(item)]
        title_candidates.sort(
            key=lambda item: (
                -float(item.get("font_size") or 0.0),
                float(item.get("y") or 1.0),
                float(item.get("x") or 1.0),
            )
        )
        title_item = title_candidates[0] if title_candidates else None
        if not title_item:
            return {}

        subtitle_candidates = [item for item in candidates if self._is_subtitle_candidate(item)]
        if title_item:
            subtitle_candidates = [
                item
                for item in subtitle_candidates
                if _item_text(item) != _item_text(title_item)
                and float(item.get("y") or 0.0) >= float(title_item.get("y") or 0.0)
            ]
        subtitle_candidates.sort(
            key=lambda item: (
                float(item.get("y") or 1.0),
                -float(item.get("font_size") or 0.0),
                float(item.get("x") or 1.0),
            )
        )
        subtitle_item = subtitle_candidates[0] if subtitle_candidates else None
        tag_candidates = [
            item
            for item in candidates
            if str(item.get("role") or "").strip().lower() in {"label", "tag", "meta"}
        ]
        tag_candidates.sort(key=lambda item: (float(item.get("y") or 1.0), float(item.get("x") or 1.0)))
        tag_item = tag_candidates[0] if tag_candidates else None
        return {
            "title": _item_text(title_item),
            "subtitle": _item_text(subtitle_item),
            "tag": _item_text(tag_item),
        }

    def _walk_cover_text_candidates(self, block: FreeformBlock, out: List[Dict[str, Any]]) -> None:
        if str(block.type or "").strip().lower() == "text_box":
            text = str(block.content or "").strip()
            if text:
                style = dict(block.style or {})
                out.append(
                    {
                        "id": str(block.id or "").strip().lower(),
                        "role": str(block.role or "").strip().lower(),
                        "text": text,
                        "x": float(block.x or 0.0),
                        "y": float(block.y or 0.0),
                        "w": float(block.w or 0.0),
                        "h": float(block.h or 0.0),
                        "font_size": float(style.get("font_size") or 0.0),
                    }
                )
        for child in list(block.children or []):
            self._walk_cover_text_candidates(child, out)

    def _build_cover_prompt(
        self,
        *,
        blueprint: FreeformDeckBlueprint,
        texts: Dict[str, str],
        cover_brief: Dict[str, Any],
    ) -> str:
        theme = blueprint.theme
        runtime = dict(blueprint.runtime or {})
        deck_brief = runtime.get("deck_brief") if isinstance(runtime.get("deck_brief"), dict) else {}
        theme_name = str(deck_brief.get("theme_factory_name") or "").strip()
        theme_rationale = str(deck_brief.get("theme_factory_rationale") or "").strip()
        visual_direction = deck_brief.get("visual_direction") if isinstance(deck_brief.get("visual_direction"), list) else []
        visual_direction_text = " | ".join(str(x).strip() for x in visual_direction if str(x).strip())[:300]
        theme_colors = deck_brief.get("theme_factory_colors") if isinstance(deck_brief.get("theme_factory_colors"), dict) else {}
        theme_color_text = ", ".join(
            f"{str(k).strip()}={str(v).strip()}"
            for k, v in theme_colors.items()
            if str(k).strip() and str(v).strip()
        )[:240]
        must_include = self._join_brief_list(cover_brief.get("must_include"))
        must_visualize = self._join_brief_list(cover_brief.get("must_visualize"))
        must_avoid = self._join_brief_list(cover_brief.get("must_avoid"))
        composition_intent = str(cover_brief.get("composition_intent") or "").strip()
        visual_center = str(cover_brief.get("visual_center") or "").strip()
        dominant_move = str(cover_brief.get("dominant_move") or "").strip()
        return (
            "Create a premium 16:9 presentation COVER BACKGROUND image only.\n"
            "Hard constraints:\n"
            "- Do NOT include any text, letters, numbers, logos, labels, or watermarks.\n"
            "- Reserve a clean text-safe area on the LEFT 45% of the canvas for WHITE overlaid title text.\n"
            "- The LEFT text-safe area MUST be dark, matte, and low-detail: deep navy/charcoal/black translucent gradient, never white, beige, pale gray, or bright.\n"
            "- Keep the LEFT text-safe area at least 4.5:1 contrast against pure white text; avoid bright highlights, glowing lines, faces, charts, or busy texture behind the title/subtitle area.\n"
            "- Keep visual focal elements on the RIGHT side.\n"
            "- Maintain a polished hero-cover look suitable for an executive presentation, not a body-content slide.\n"
            "- Favor strong contrast, crisp shapes, complete closed outlines, and clearly readable visual elements.\n"
            "- Avoid washed-out white emptiness, broken rings, clipped icons, faint linework, or barely-visible decorative elements.\n"
            "- This cover should feel like a finished hero visual, not a sparse wireframe or an inner content page.\n"
            f"- Theme style: {theme_name or 'default'}.\n"
            f"- Theme rationale: {theme_rationale or 'keep the deck visually coherent and presentation-grade'}.\n"
            f"- Theme color family for inspiration only: {theme_color_text or f'primary family around accent {theme.accent_color}'}.\n"
            f"- Deck-level visual direction: {visual_direction_text or 'business presentation, clean hierarchy'}.\n"
            f"- Cover composition intent: {composition_intent or 'hero cover with left text-safe area and right-side focal visual'}.\n"
            f"- Cover visual center: {visual_center or 'right-side focal hero element cluster'}.\n"
            f"- Cover dominant move: {dominant_move or 'strong right-side visual with spacious left text area'}.\n"
            f"- Must contain these visual ideas or motifs: {must_include or 'cover hero artwork, clear title-safe region, subtle metadata support area'}.\n"
            f"- Must visually support these cover ideas without rendering text: {must_visualize or 'hero title area, secondary metadata, time-span or presenter metadata'}.\n"
            f"- Must avoid these directions: {must_avoid or 'generic report page look, repeated inner-page layout patterns'}.\n"
            "- Keep the result coherent with the deck theme, but do not copy inner-page backgrounds or literal layout tokens.\n"
            f"- Context title (for style reference only, DO NOT render text): {texts.get('title', '')[:120]}\n"
            f"- Context subtitle (for style reference only, DO NOT render text): {texts.get('subtitle', '')[:160]}\n"
        )

    async def _generate_cover_background(self, *, prompt: str, user_id: str) -> Optional[str]:
        try:
            result = await generate_image(
                prompt=prompt,
                user_id=user_id,
                log_hook=self._log_image_event,
            )
            image_bytes = result.image_bytes
            normalized = self._normalize_cover_bytes(image_bytes)
            uploader = AliyunOSSUploader()
            _public, object_path = uploader.upload_bytes_with_path(
                normalized,
                user_id=str(user_id or "anonymous").strip() or "anonymous",
                file_name=f"presentation_cover_bg_{uuid.uuid4().hex[:10]}.png",
                content_type="image/png",
            )
            return uploader.sign_url(object_path)
        except Exception:
            logger.warning("presentation_cover_image_gen_exception", exc_info=True)
            return None

    def _log_image_event(self, event: str, payload: Dict[str, Any]) -> None:
        if event == "image_generation_response" and int(payload.get("status_code") or 0) >= 400:
            logger.warning(
                "presentation_cover_event",
                extra={
                    "event": f"presentation_cover.{event}",
                    "cover_payload": payload,
                },
            )
            return
        logger.info(
            "presentation_cover_event",
            extra={
                "event": f"presentation_cover.{event}",
                "cover_payload": payload,
            },
        )

    def _normalize_cover_bytes(self, image_bytes: bytes) -> bytes:
        with Image.open(BytesIO(image_bytes)) as img:
            rgb = img.convert("RGB")
            if rgb.size != (1600, 900):
                rgb = rgb.resize((1600, 900), Image.Resampling.LANCZOS)
            out = BytesIO()
            rgb.save(out, format="PNG")
            return out.getvalue()

    def _rebuild_cover_page(
        self,
        *,
        page: FreeformPageBlueprint,
        image_url: str,
        texts: Dict[str, str],
        theme: Dict[str, Any],
        deck_runtime: Dict[str, Any],
    ) -> FreeformPageBlueprint:
        title = str(texts.get("title") or "").strip()
        subtitle = str(texts.get("subtitle") or "").strip()
        tag = str(texts.get("tag") or "").strip()
        deck_brief = deck_runtime.get("deck_brief") if isinstance(deck_runtime.get("deck_brief"), dict) else {}
        design_tokens = deck_brief.get("design_tokens") if isinstance(deck_brief.get("design_tokens"), dict) else {}
        title_size = int(design_tokens.get("title_font_size") or 56)
        subtitle_size = int(design_tokens.get("subtitle_font_size") or 28)
        body_size = int(design_tokens.get("body_font_size") or 22)
        font_family = str(theme.get("font_family") or design_tokens.get("font_family") or "'PingFang SC', 'Microsoft YaHei', sans-serif")
        accent = str(theme.get("accent_color") or design_tokens.get("accent_color") or "#38bdf8")
        title_color = "#ffffff"
        body_color = "#dbe7f5"

        blocks: List[FreeformBlock] = [
            FreeformBlock(
                id=f"{page.page_id}_cover_bg",
                type="image",
                role="background",
                x=0.0,
                y=0.0,
                w=1.0,
                h=1.0,
                z_index=0,
                content=image_url,
                style={
                    "fit": "cover",
                },
            ),
            FreeformBlock(
                id=f"{page.page_id}_cover_text_scrim",
                type="rectangle",
                role="surface",
                x=0.0,
                y=0.0,
                w=0.56,
                h=1.0,
                z_index=1,
                style={
                    "background": "linear-gradient(90deg, rgba(6, 14, 28, 0.86) 0%, rgba(6, 14, 28, 0.70) 58%, rgba(6, 14, 28, 0.00) 100%)",
                },
            ),
            FreeformBlock(
                id=f"{page.page_id}_cover_accent",
                type="rectangle",
                role="accent",
                x=0.07,
                y=0.20,
                w=0.09,
                h=0.008,
                z_index=2,
                style={
                    "background": accent,
                    "border_radius": 8,
                },
            ),
            FreeformBlock(
                id=f"{page.page_id}_cover_title",
                type="text_box",
                role="title",
                x=0.07,
                y=0.24,
                w=0.45,
                h=0.28,
                z_index=3,
                content=title,
                style={
                    "font_size": title_size,
                    "font_weight": "bold",
                    "color": title_color,
                    "line_height": 1.12,
                    "font_family": font_family,
                    "text_align": "left",
                },
            ),
        ]
        if subtitle:
            blocks.append(
                FreeformBlock(
                    id=f"{page.page_id}_cover_subtitle",
                    type="text_box",
                    role="subtitle",
                    x=0.07,
                    y=0.56,
                    w=0.44,
                    h=0.13,
                    z_index=3,
                    content=subtitle,
                    style={
                        "font_size": subtitle_size,
                        "font_weight": "normal",
                        "color": body_color,
                        "line_height": 1.25,
                        "font_family": font_family,
                        "text_align": "left",
                    },
                )
            )
        if tag:
            blocks.append(
                FreeformBlock(
                    id=f"{page.page_id}_cover_tag_text",
                    type="text_box",
                    role="label",
                    x=0.07,
                    y=0.76,
                    w=0.30,
                    h=0.04,
                    z_index=4,
                    content=tag,
                    style={
                        "font_size": body_size,
                        "font_weight": "semibold",
                        "color": title_color,
                        "font_family": font_family,
                        "text_align": "left",
                    },
                )
            )

        page_out = page.model_copy(deep=True)
        page_out.layout_type = "cover_programmatic_image_text"
        page_out.blocks = blocks
        if not str(page_out.page_title or "").strip():
            page_out.page_title = title
        if not str(page_out.page_subtitle or "").strip():
            page_out.page_subtitle = subtitle
        return page_out

    def _extract_cover_copy_from_brief(self, cover_brief: Dict[str, Any]) -> Dict[str, str]:
        must_include = list(cover_brief.get("must_include") or [])
        must_visualize = list(cover_brief.get("must_visualize") or [])
        all_items = must_include + must_visualize
        title = self._extract_prefixed_value(all_items, ("主标题", "标题", "title"))
        if not title:
            title = self._extract_quoted_title(str(cover_brief.get("visual_center") or "").strip())
        subtitle = self._extract_prefixed_value(all_items, ("副标题", "subtitle"))
        presenter = self._extract_prefixed_value(all_items, ("汇报人", "演讲者", "presenter", "speaker"))
        if not presenter and self._contains_presenter_slot(all_items):
            presenter = self._default_presenter_tag({})
        return {
            "title": title,
            "subtitle": subtitle,
            "tag": presenter or "",
        }

    def _fallback_cover_copy(
        self,
        *,
        deck_runtime: Dict[str, Any],
        page: FreeformPageBlueprint,
        cover_brief: Dict[str, Any],
    ) -> Dict[str, str]:
        deck_brief = deck_runtime.get("deck_brief") if isinstance(deck_runtime.get("deck_brief"), dict) else {}
        title = self._infer_cover_title(deck_brief=deck_brief, page=page, cover_brief=cover_brief)
        subtitle = self._infer_cover_subtitle(deck_brief=deck_brief, cover_brief=cover_brief)
        return {
            "title": title,
            "subtitle": subtitle,
            "tag": self._default_presenter_tag(deck_runtime),
        }

    def _infer_cover_title(self, *, deck_brief: Dict[str, Any], page: FreeformPageBlueprint, cover_brief: Dict[str, Any]) -> str:
        title = str(page.page_title or "").strip()
        if title:
            return title
        visual_center = str(cover_brief.get("visual_center") or "").strip()
        quoted = self._extract_quoted_title(visual_center)
        if quoted:
            return quoted
        key_takeaway = str(cover_brief.get("key_takeaway") or "").strip()
        if key_takeaway:
            return key_takeaway
        deck_goal = str(deck_brief.get("deck_goal") or "").strip()
        if deck_goal:
            return deck_goal
        page_goal = str(cover_brief.get("page_goal") or "").strip()
        if page_goal and len(page_goal) <= 28 and not self._looks_like_sentence(page_goal):
            return page_goal
        source_outline = str(cover_brief.get("source_outline_section") or "").strip()
        if source_outline and source_outline != "封面页":
            return source_outline
        return ""

    def _infer_cover_subtitle(self, *, deck_brief: Dict[str, Any], cover_brief: Dict[str, Any]) -> str:
        _ = deck_brief
        _ = cover_brief
        return ""

    def _default_presenter_tag(self, deck_runtime: Dict[str, Any]) -> str:
        return "汇报人：________"

    @staticmethod
    def _extract_prefixed_value(items: List[Any], prefixes: tuple[str, ...]) -> str:
        for raw in items:
            text = str(raw or "").strip()
            if not text:
                continue
            normalized = text.replace("：", ":")
            for prefix in prefixes:
                token = f"{prefix}:"
                if normalized.lower().startswith(token.lower()):
                    return normalized.split(":", 1)[1].strip()
        return ""

    @staticmethod
    def _extract_quoted_title(text: str) -> str:
        raw = str(text or "").strip()
        if not raw:
            return ""
        pairs = (("《", "》"), ("“", "”"), ("\"", "\""), ("'", "'"))
        for left, right in pairs:
            start = raw.find(left)
            if start < 0:
                continue
            end = raw.find(right, start + len(left))
            if end <= start:
                continue
            value = raw[start + len(left):end].strip()
            if value:
                return value
        return ""

    @classmethod
    def _contains_presenter_slot(cls, items: List[Any]) -> bool:
        for raw in items:
            text = str(raw or "").strip()
            if not text:
                continue
            if any(token in text for token in ("汇报人", "演讲者", "speaker", "presenter", "场景说明")):
                return True
        return False

    @staticmethod
    def _join_brief_list(value: Any) -> str:
        if not isinstance(value, list):
            return ""
        return " | ".join(str(item).strip() for item in value if str(item).strip())[:400]

    @staticmethod
    def _trim_cover_text(text: str, limit: int) -> str:
        raw = str(text or "").strip()
        return raw[:limit].rstrip("：:，,。.;；")

    @staticmethod
    def _is_title_candidate(item: Dict[str, Any]) -> bool:
        role = str(item.get("role") or "").strip().lower()
        block_id = str(item.get("id") or "").strip().lower()
        y = float(item.get("y") or 0.0)
        font_size = float(item.get("font_size") or 0.0)
        if y > 0.68:
            return False
        if role in {"title", "headline", "heading"}:
            return True
        return (
            font_size >= 28.0
            and any(token in block_id for token in ("headline", "title", "heading"))
        )

    @staticmethod
    def _is_subtitle_candidate(item: Dict[str, Any]) -> bool:
        role = str(item.get("role") or "").strip().lower()
        block_id = str(item.get("id") or "").strip().lower()
        y = float(item.get("y") or 0.0)
        if y > 0.82:
            return False
        if role in {"subtitle", "subline"}:
            return True
        return any(token in block_id for token in ("subtitle", "subline"))

    @staticmethod
    def _looks_like_sentence(text: str) -> bool:
        raw = str(text or "").strip()
        if not raw:
            return False
        if any(mark in raw for mark in ("。", "！", "？", ".", "!", "?")):
            return True
        return len(raw) > 24 and any(token in raw for token in ("是", "将", "正在", "通过", "帮助", "建立", "走向"))
