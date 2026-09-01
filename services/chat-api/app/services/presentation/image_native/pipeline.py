from __future__ import annotations

import inspect
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.services.presentation.debug_dumper import dump_collision_only_report
from app.services.presentation.geometry_collision_detector import detect_deck_collisions
from app.services.presentation.html_renderer import HtmlRenderer
from app.services.presentation.image_filler import ImageFiller
from app.services.presentation.image_native.page_planner import ImageNativePagePlanner
from app.services.presentation.preview_bundle import PreviewBundleBuilder
from app.services.presentation.story_planner import StoryPlanner
from app.services.presentation.structural_sanitizer import sanitize_deck

logger = logging.getLogger(__name__)


class ImageNativePresentationPipeline:
    """End-to-end PPT pipeline using complete image visual -> semantic rebuild."""

    def __init__(self) -> None:
        self._story_planner = StoryPlanner()
        self._page_planner = ImageNativePagePlanner()
        self._html_renderer = HtmlRenderer()
        self._bundle_builder = PreviewBundleBuilder()
        self._image_filler = ImageFiller()

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
            logger.warning("presentation_image_native_progress_emit_failed payload=%s", payload, exc_info=True)

    async def build(
        self,
        *,
        messages: List[Any],
        output_spec: Dict[str, Any],
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None] | None]] = None,
    ) -> Dict[str, Any]:
        enriched_output_spec = dict(output_spec or {})
        enriched_output_spec["presentation_pipeline_version"] = "image_rebuild"
        enriched_output_spec["presentation_generation_mode"] = "image_rebuild"

        await self._emit_progress(
            progress_callback,
            {
                "stage": "story_planning",
                "status": "running",
                "kind": "analyze",
                "message": "正在生成PPT故事线",
            },
        )
        story_plan = await self._story_planner.build(messages=messages, output_spec=enriched_output_spec)
        logger.info(
            "presentation_image_native_stage stage=story_ready deck_id=%s page_count=%s",
            str(story_plan.deck_id or "").strip(),
            len(list(story_plan.pages or [])),
        )

        blueprint = await self._page_planner.build(
            story_plan=story_plan,
            request_context={"messages": messages, "output_spec": enriched_output_spec},
            progress_callback=progress_callback,
        )
        blueprint = sanitize_deck(blueprint)

        await self._emit_progress(
            progress_callback,
            {
                "stage": "image_generation",
                "status": "running",
                "kind": "render",
                "message": "正在补齐页面图片资源",
            },
        )
        blueprint = await self._image_filler.fill(
            blueprint,
            user_id=str(enriched_output_spec.get("user_id") or "anonymous"),
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

        collision_report = detect_deck_collisions(blueprint)
        blueprint.runtime = dict(blueprint.runtime or {})
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
        try:
            dump_collision_only_report(blueprint=blueprint, collision_report=collision_report)
        except Exception:
            logger.warning(
                "presentation_image_native_stage stage=collision_dump_failed deck_id=%s",
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
            "presentation_image_native_stage stage=preview_ready deck_id=%s slide_count=%s",
            str(blueprint.deck_id or "").strip(),
            len(list(blueprint.pages or [])),
        )
        return {
            "story_plan": story_plan,
            "blueprint_result": blueprint,
            "html_preview": html_preview,
            "preview_bundle": preview_bundle,
            "document_payload": document_payload,
        }
