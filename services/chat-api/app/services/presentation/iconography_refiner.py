"""Deck-level semantic icon refinement for LLM-authored presentations.

The page composer remains responsible for layout.  This pass only finishes the
icon system it authored: it replaces generic/repeated choices with icons selected
from MOVO's existing Tabler library and harmonizes supporting icon scale with the
nearby copy.  It never adds containers or rewrites page geometry.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

from app.services.presentation.contracts import FreeformBlock, FreeformDeckBlueprint
from app.services.presentation.icon_library import (
    choose_icons_with_llm,
    load_inline_svg_map,
    resolve_icon_from_texts,
    resolve_icon_name,
)

logger = logging.getLogger(__name__)


@dataclass
class _IconSlot:
    block: FreeformBlock
    page_id: str
    title: str
    body: str
    meta: str
    frame_width_px: float
    frame_height_px: float
    peer_font_size: float | None


class IconographyRefiner:
    """Apply one coherent semantic icon pass across the generated deck."""

    _MAX_LLM_SLOTS = 48
    _PRESERVE_ROLE_HINTS = ("hero", "anchor", "logo", "brand", "decor", "background")

    async def refine(self, blueprint: FreeformDeckBlueprint) -> FreeformDeckBlueprint:
        out = blueprint.model_copy(deep=True)
        slots: List[_IconSlot] = []
        for page in list(out.pages or []):
            page_context = " ".join(
                part for part in (str(page.page_title or "").strip(), str(page.page_subtitle or "").strip())
                if part
            )
            self._collect_slots(
                blocks=list(page.blocks or []),
                page_id=str(page.page_id or "").strip(),
                page_context=page_context,
                frame_width_px=1600.0,
                frame_height_px=900.0,
                slots=slots,
            )
        if not slots:
            return out

        llm_slots = slots[: self._MAX_LLM_SLOTS]
        chosen = await choose_icons_with_llm(
            slot_id=str(out.deck_id or "presentation"),
            items=[{"title": slot.title, "body": slot.body, "meta": slot.meta} for slot in llm_slots],
            icon_prompt="Choose a coherent, restrained icon family for this full deck.",
        )
        svg_map = load_inline_svg_map()
        for index, slot in enumerate(slots):
            icon_name = chosen[index] if index < len(chosen) else self._fallback_icon(slot)
            icon_name = resolve_icon_name(icon_name, fallback="")
            if not icon_name:
                continue
            slot.block.icon = icon_name
            slot.block.icon_svg = str(svg_map.get(icon_name) or "")
            self._harmonize_supporting_size(slot)

        out.runtime = dict(out.runtime or {})
        out.runtime["iconography_refiner"] = {
            "slot_count": len(slots),
            "llm_selected_count": min(len(chosen), len(llm_slots)),
            "version": "2026-08-31",
        }
        logger.info(
            "presentation_iconography_refined deck_id=%s slots=%s llm_selected=%s",
            str(out.deck_id or "").strip(),
            len(slots),
            min(len(chosen), len(llm_slots)),
        )
        return out

    def _collect_slots(
        self,
        *,
        blocks: Sequence[FreeformBlock],
        page_id: str,
        page_context: str,
        frame_width_px: float,
        frame_height_px: float,
        slots: List[_IconSlot],
    ) -> None:
        peers = list(blocks or [])
        text_peers = [block for block in peers if str(block.type or "").lower() == "text_box" and str(block.content or "").strip()]
        for block in peers:
            block_type = str(block.type or "").strip().lower()
            if block_type == "icon":
                nearby = sorted(text_peers, key=lambda text: self._distance(block, text))[:2]
                title = str(nearby[0].content or "").strip() if nearby else str(block.content or "").strip()
                body = str(nearby[1].content or "").strip() if len(nearby) > 1 else ""
                peer_size = self._font_size(nearby[0]) if nearby else None
                slots.append(_IconSlot(
                    block=block,
                    page_id=page_id,
                    title=title,
                    body=body,
                    meta=f"{page_context} | role={block.role} | current_icon={block.icon}",
                    frame_width_px=max(1.0, frame_width_px),
                    frame_height_px=max(1.0, frame_height_px),
                    peer_font_size=peer_size,
                ))
            if block.children:
                if str(block.coordinate_space or "page").lower() == "parent":
                    child_width = max(1.0, frame_width_px * float(block.w or 0.0))
                    child_height = max(1.0, frame_height_px * float(block.h or 0.0))
                else:
                    child_width = max(1.0, 1600.0 * float(block.w or 0.0))
                    child_height = max(1.0, 900.0 * float(block.h or 0.0))
                self._collect_slots(
                    blocks=list(block.children or []),
                    page_id=page_id,
                    page_context=page_context,
                    frame_width_px=child_width,
                    frame_height_px=child_height,
                    slots=slots,
                )

    @staticmethod
    def _distance(left: FreeformBlock, right: FreeformBlock) -> float:
        left_x = float(left.x or 0.0) + float(left.w or 0.0) / 2.0
        left_y = float(left.y or 0.0) + float(left.h or 0.0) / 2.0
        right_x = float(right.x or 0.0) + float(right.w or 0.0) / 2.0
        right_y = float(right.y or 0.0) + float(right.h or 0.0) / 2.0
        return (left_x - right_x) ** 2 + (left_y - right_y) ** 2

    @staticmethod
    def _font_size(block: FreeformBlock) -> float | None:
        try:
            return float(dict(block.style or {}).get("font_size"))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _fallback_icon(slot: _IconSlot) -> str:
        return resolve_icon_from_texts(slot.title, slot.body, slot.meta, fallback=str(slot.block.icon or ""))

    def _harmonize_supporting_size(self, slot: _IconSlot) -> None:
        role = str(slot.block.role or "").strip().lower()
        if any(hint in role for hint in self._PRESERVE_ROLE_HINTS):
            return
        if slot.peer_font_size is None:
            return
        font_size = slot.peer_font_size
        target_px = 32.0 if font_size <= 20 else 36.0 if font_size <= 24 else 40.0 if font_size <= 32 else 46.0
        new_w = min(0.24, target_px / slot.frame_width_px)
        new_h = min(0.30, target_px / slot.frame_height_px)
        center_x = float(slot.block.x or 0.0) + float(slot.block.w or 0.0) / 2.0
        center_y = float(slot.block.y or 0.0) + float(slot.block.h or 0.0) / 2.0
        slot.block.w = new_w
        slot.block.h = new_h
        slot.block.x = max(0.0, min(1.0 - new_w, center_x - new_w / 2.0))
        slot.block.y = max(0.0, min(1.0 - new_h, center_y - new_h / 2.0))


__all__ = ["IconographyRefiner"]
