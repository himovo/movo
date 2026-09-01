from __future__ import annotations

import inspect
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.services.presentation.story_planner import StoryPlanner
from app.services.presentation.freeform_page_planner import FreeformPagePlanner
from app.services.presentation.html_renderer import HtmlRenderer
from app.services.presentation.debug_dumper import dump_collision_only_report
from app.services.presentation.geometry_collision_detector import (
    detect_deck_collisions,
)
from app.services.presentation.image_filler import ImageFiller
from app.services.presentation.preview_bundle import PreviewBundleBuilder
from app.services.presentation.structural_sanitizer import sanitize_deck
from app.services.presentation.cover_image_composer import CoverImageComposer
from app.services.presentation.style_contract import PresentationStyleContract
from app.services.presentation.iconography_refiner import IconographyRefiner

logger = logging.getLogger(__name__)


class PresentationPipeline:
    """End-to-end build pipeline.

    The pipeline trusts the LLM's first-shot page geometry. After the LLM
    produces each page, the pipeline performs one deck-level semantic finishing
    pass and deterministic safe-cleanup:

      • ``IconographyRefiner`` — chooses coherent icons from the existing MOVO
        library and aligns supporting icon scale with nearby copy. No layout rewrite.
      • ``sanitize_deck`` — fixes unrenderable bugs (HTML tag leakage in text,
        zero-geometry decoration, etc.). Does not touch coordinates.
      • Empty-page rebuild — re-invokes the LLM only when a page literally has
        no visible text. Single-shot, no repair loop.
      • Collision diagnostics — pure logging; never modifies the deck.
    """

    def __init__(self) -> None:
        self._story_planner = StoryPlanner()
        self._page_planner = FreeformPagePlanner()
        self._html_renderer = HtmlRenderer()
        self._bundle_builder = PreviewBundleBuilder()
        self._image_filler = ImageFiller()
        self._cover_composer = CoverImageComposer()
        self._style_contract = PresentationStyleContract()
        self._iconography_refiner = IconographyRefiner()

    async def _emit_progress(
        self,
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None] | None]],
        payload: Dict[str, Any],
    ) -> None:
        if progress_callback is None:
            return
        try:
            result = progress_callback(dict(payload or {}))
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.warning("presentation_stage stage=progress_emit_failed payload=%s", payload, exc_info=True)

    async def build(
        self,
        *,
        messages: List[Any],
        output_spec: Dict[str, Any],
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None] | None]] = None,
    ) -> Dict[str, Any]:
        enriched_output_spec = dict(output_spec or {})
        enriched_output_spec["presentation_pipeline_version"] = "llm"
        logger.info(
            "presentation_stage stage=build_start message_count=%s has_task_id=%s",
            len(list(messages or [])),
            bool(str(enriched_output_spec.get("task_id") or "").strip()),
        )
        await self._emit_progress(
            progress_callback,
            {
                "stage": "story_planning",
                "status": "running",
                "kind": "analyze",
                "message": "正在生成PPT故事线",
            },
        )
        story_plan = await self._story_planner.build(
            messages=messages, output_spec=enriched_output_spec
        )
        logger.info(
            "presentation_stage stage=story_ready deck_id=%s page_count=%s",
            str(story_plan.deck_id or "").strip(),
            len(list(story_plan.pages or [])),
        )
        blueprint = await self._page_planner.build(
            story_plan=story_plan,
            request_context={
                "messages": messages,
                "output_spec": enriched_output_spec,
            },
            progress_callback=progress_callback,
        )
        logger.info(
            "presentation_stage stage=blueprint_ready deck_id=%s page_count=%s",
            str(blueprint.deck_id or "").strip(),
            len(list(blueprint.pages or [])),
        )
        blueprint.runtime = dict(blueprint.runtime or {})

        # ── Empty page repair: detect pages with no visible text and rebuild ──
        empty_page_ids = self._detect_empty_pages(blueprint)
        if empty_page_ids:
            logger.warning(
                "presentation_stage stage=empty_page_repair deck_id=%s empty_pages=%s",
                str(blueprint.deck_id or "").strip(),
                empty_page_ids,
            )
            blueprint = await self._page_planner.rebuild_failed_pages(
                blueprint=blueprint,
                failed_page_ids=empty_page_ids,
            )
            still_empty = self._detect_empty_pages(blueprint)
            if still_empty:
                logger.warning(
                    "presentation_stage stage=empty_page_repair_failed deck_id=%s still_empty=%s",
                    str(blueprint.deck_id or "").strip(),
                    still_empty,
                )

        # Finish the icon system once at deck level.  The page composer still
        # owns layout; this pass only makes its semantic symbols coherent and
        # proportionate to their nearby copy.
        blueprint = await self._iconography_refiner.refine(blueprint)

        # Canonical style boundary + deterministic safe cleanup. Neither step
        # changes geometry; they make preview/editor/export consume one schema.
        blueprint = self._style_contract.canonicalize(blueprint)
        blueprint = sanitize_deck(blueprint)

        # Fill placeholder image blocks with generated images. Runs after
        # sanitize so any pruned/fixed image blocks are no longer part of
        # the target set; runs before html/pptx render so the output never
        # shows the dashed-border placeholder when a real image is available.
        await self._emit_progress(
            progress_callback,
            {
                "stage": "image_generation",
                "status": "running",
                "kind": "render",
                "message": "正在生成页面图片资源",
            },
        )
        blueprint = await self._image_filler.fill(
            blueprint,
            user_id=str(enriched_output_spec.get("user_id") or "anonymous"),
        )
        try:
            await self._emit_progress(
                progress_callback,
                {
                    "stage": "cover_generation",
                    "status": "running",
                    "kind": "render",
                    "message": "正在生成封面背景图",
                },
            )
            blueprint = await self._cover_composer.compose(
                blueprint=blueprint,
                user_id=str(enriched_output_spec.get("user_id") or "anonymous"),
                preserve_layout=True,
            )
        except Exception:
            logger.warning(
                "presentation_stage stage=cover_compose_failed deck_id=%s",
                str(blueprint.deck_id or "").strip(),
                exc_info=True,
            )

        # Image and cover composers may add new blocks. Canonicalize once more
        # before every downstream renderer sees the blueprint.
        blueprint = self._style_contract.canonicalize(blueprint)

        logger.info(
            "presentation_stage stage=renderable_ready deck_id=%s page_count=%s",
            str(blueprint.deck_id or "").strip(),
            len(list(blueprint.pages or [])),
        )
        await self._emit_progress(
            progress_callback,
            {
                "stage": "preview_render",
                "status": "running",
                "kind": "render",
                "message": "正在生成PPT预览",
            },
        )
        html_preview = self._html_renderer.compile(blueprint=blueprint)
        logger.info(
            "presentation_stage stage=html_ready deck_id=%s slide_count=%s",
            str(blueprint.deck_id or "").strip(),
            int(html_preview.slide_count or 0),
        )

        # ── Collision diagnostics (no repair, just observation + dump) ──
        collision_report = detect_deck_collisions(blueprint)
        blueprint.runtime["collision_report"] = {
            "deck_id": collision_report.deck_id,
            "failed_page_ids": list(collision_report.failed_page_ids),
            "total_defect_count": int(collision_report.total_defect_count),
            "pages": [
                {
                    "page_id": p.page_id,
                    "defect_count": len(p.defects),
                    "defects": [d.to_dict() for d in p.defects],
                }
                for p in collision_report.pages
            ],
        }
        has_collision_issue = bool(list(collision_report.failed_page_ids))
        _collision_logger = logger.warning if has_collision_issue else logger.info
        _collision_logger(
            "presentation_stage stage=collision_diagnostics_done deck_id=%s "
            "failed_pages=%s total_defects=%s",
            str(blueprint.deck_id or "").strip(),
            list(collision_report.failed_page_ids),
            collision_report.total_defect_count,
        )
        try:
            dump_collision_only_report(
                blueprint=blueprint,
                collision_report=collision_report,
            )
        except Exception:
            logger.warning(
                "presentation_stage stage=collision_dump_failed deck_id=%s",
                str(blueprint.deck_id or "").strip(),
                exc_info=True,
            )

        preview_bundle, document_payload = self._bundle_builder.build(
            blueprint=blueprint.model_dump(),
            compile_result=html_preview,
            user_id=str(enriched_output_spec.get("user_id") or "anonymous"),
            task_id=str(story_plan.deck_id or "presentation"),
        )
        logger.info(
            "presentation_stage stage=preview_ready deck_id=%s html_preview_url=%s",
            str(blueprint.deck_id or "").strip(),
            str(getattr(preview_bundle.html_preview, "url", "") or "").strip(),
        )
        return {
            "story_plan": story_plan,
            "blueprint_result": blueprint,
            "html_preview": html_preview,
            "preview_bundle": preview_bundle,
            "document_payload": document_payload,
        }

    @staticmethod
    def _detect_empty_pages(blueprint) -> List[str]:
        """Detect pages where no text_box has any visible content."""
        empty_ids: List[str] = []
        for page in list(blueprint.pages or []):
            page_id = str(page.page_id or "").strip()
            if not page_id:
                continue
            has_text = False
            for block in list(page.blocks or []):
                if PresentationPipeline._block_has_text(block):
                    has_text = True
                    break
            if not has_text:
                empty_ids.append(page_id)
        return empty_ids

    @staticmethod
    def _block_has_text(block) -> bool:
        """Recursively check if a block or its children contain visible text."""
        if str(block.type or "").strip().lower() == "text_box":
            if str(block.content or "").strip():
                return True
        for child in list(block.children or []):
            if PresentationPipeline._block_has_text(child):
                return True
        return False
