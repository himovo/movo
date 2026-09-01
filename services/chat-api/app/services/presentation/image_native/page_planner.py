from __future__ import annotations

import asyncio
import inspect
import json
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.core.config import get_settings
from app.llm.configured_multimodal import ConfiguredMultimodalClient
from app.services.presentation.brief_compiler import BriefCompiler
from app.services.presentation.contracts import (
    ConstraintBundle,
    DeckBrief,
    FreeformDeckBlueprint,
    FreeformPageBlueprint,
    PageBrief,
    PageRepairReport,
    StoryDeckPlan,
)
from app.services.presentation.freeform_page_planner import FreeformPagePlanner
from app.services.presentation.image_native.blueprint_mapper import (
    BlueprintComposer,
    fallback_page_from_analysis,
)
from app.services.presentation.image_native.blueprint_postprocess import postprocess_image_native_page
from app.services.presentation.image_native.contracts import ImageNativePagePlan
from app.services.presentation.image_native.image_generator import (
    FullSlideImageGenerator,
    ImageNativeAssetGenerator,
)
from app.services.presentation.image_native.icon_generator import ImageNativeIconSvgGenerator
from app.services.presentation.image_native.prompt_builder import (
    build_page_plan_prompt,
    constrain_full_slide_prompt,
)
from app.services.presentation.image_native.visual_analyzer import VisualSemanticAnalyzer
from app.services.presentation.theme_factory_catalog import build_freeform_theme_from_design_tokens
from app.services.presentation.execution.session import PresentationExecutionSession

logger = logging.getLogger(__name__)


class ImageNativePagePlanner:
    """Page planner that uses gpt-image-2 as the visual design source.

    It preserves the production deck/story planning contracts and emits the
    same FreeformDeckBlueprint consumed by preview, editor, and PPTX export.
    """

    def __init__(self) -> None:
        self._legacy_helper = FreeformPagePlanner()
        self._brief_compiler = BriefCompiler()
        self._responses = ConfiguredMultimodalClient()
        self._slide_generator = FullSlideImageGenerator()
        self._visual_analyzer = VisualSemanticAnalyzer()
        self._asset_generator = ImageNativeAssetGenerator()
        self._icon_generator = ImageNativeIconSvgGenerator()
        self._blueprint_composer = BlueprintComposer()

    async def _emit_progress(
        self,
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None] | None]],
        payload: Dict[str, Any],
    ) -> None:
        if progress_callback is None:
            return
        result = progress_callback(dict(payload or {}))
        if inspect.isawaitable(result):
            await result

    async def build(
        self,
        *,
        story_plan: StoryDeckPlan,
        request_context: Dict[str, Any] | None = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None] | None]] = None,
        execution_session: PresentationExecutionSession | None = None,
    ) -> FreeformDeckBlueprint:
        messages = list((request_context or {}).get("messages") or [])
        output_spec = dict((request_context or {}).get("output_spec") or {})
        user_id = str(output_spec.get("user_id") or "anonymous").strip() or "anonymous"
        session_id = str(output_spec.get("session_id") or output_spec.get("task_id") or story_plan.deck_id or "").strip()

        user_outline = self._legacy_helper._extract_user_outline(messages=messages, output_spec=output_spec)
        generation_guidance = self._legacy_helper._extract_generation_guidance(messages=messages, output_spec=output_spec)
        user_message_context = self._legacy_helper._extract_message_text(messages)
        constraint_bundle = self._brief_compiler.build_constraint_bundle(
            output_spec=output_spec,
            user_outline=user_outline,
            user_generation_guidance=generation_guidance,
            user_message_context=user_message_context,
        )
        restored_planning = dict(execution_session.planning) if execution_session is not None else {}
        try:
            deck_brief = DeckBrief.model_validate(restored_planning["image_native_deck_brief"])
        except Exception:
            deck_brief = await self._legacy_helper._build_deck_brief(
                story_plan=story_plan,
                constraint_bundle=constraint_bundle,
                user_message_context=user_message_context,
            )
            deck_brief = self._legacy_helper._resolve_deck_theme(deck_brief, constraint_bundle=constraint_bundle)
            if execution_session is not None:
                await execution_session.checkpoint_planning({
                    "image_native_deck_brief": deck_brief.model_dump(),
                })

        await self._emit_progress(
            progress_callback,
            {
                "stage": "deck_planning",
                "status": "running",
                "kind": "analyze",
                "message": "正在规划 image-native PPT 视觉路线",
            },
        )

        built_pages: List[FreeformPageBlueprint] = []
        repair_reports: List[PageRepairReport] = []
        page_artifacts: List[Dict[str, Any]] = []
        page_briefs = list(deck_brief.page_briefs or [])
        page_count = len(page_briefs)
        page_concurrency = self._page_concurrency(page_count)
        restored_pages: Dict[str, tuple[FreeformPageBlueprint, Dict[str, Any]]] = {}
        if execution_session is not None:
            for page_id, checkpoint in execution_session.pages.items():
                try:
                    restored_pages[page_id] = (
                        FreeformPageBlueprint.model_validate(checkpoint.get("blueprint", checkpoint)),
                        dict(checkpoint.get("metadata") or {}),
                    )
                except Exception:
                    logger.warning(
                        "presentation_image_native_checkpoint_invalid job_id=%s page_id=%s",
                        execution_session.job_id,
                        page_id,
                        exc_info=True,
                    )

        if page_concurrency <= 1 or page_count <= 1:
            for idx, page_brief in enumerate(page_briefs):
                page_id = str(page_brief.page_id or "").strip()
                if page_id in restored_pages:
                    page, artifact = restored_pages[page_id]
                    built_pages.append(page)
                    page_artifacts.append(artifact)
                    repair_reports.append(self._repair_report(page))
                    continue
                if execution_session is not None:
                    execution_session.raise_if_cancelled()
                page_label = self._legacy_helper._progress_page_label(page_brief, idx + 1)
                await self._emit_progress(
                    progress_callback,
                    {
                        "stage": "image_native_page_generation",
                        "status": "running",
                        "kind": "write",
                        "page_index": idx + 1,
                        "page_total": page_count,
                        "page_id": str(page_brief.page_id or "").strip(),
                        "page_label": page_label,
                        "message": f"正在用 image-native 路线生成第{idx + 1}页：{page_label}",
                    },
                )
                page, artifact = await self._build_one_page(
                    deck_brief=deck_brief,
                    constraint_bundle=constraint_bundle,
                    page_brief=page_brief,
                    built_pages=built_pages,
                    user_id=user_id,
                    session_id=session_id,
                )
                built_pages.append(page)
                page_artifacts.append(artifact)
                repair_reports.append(self._repair_report(page))
                if execution_session is not None:
                    await execution_session.checkpoint_page(
                        page_id,
                        page.model_dump(),
                        metadata=artifact,
                    )
                logger.info(
                    "presentation_image_native_page_ready page_id=%s block_count=%s",
                    str(page.page_id or "").strip(),
                    len(list(page.blocks or [])),
                )
        else:
            logger.info(
                "presentation_image_native_page_parallel_start deck_id=%s page_count=%s concurrency=%s",
                str(deck_brief.deck_id or story_plan.deck_id or "").strip(),
                page_count,
                page_concurrency,
            )
            sem = asyncio.Semaphore(page_concurrency)
            ordered_results: List[tuple[FreeformPageBlueprint, Dict[str, Any]] | None] = [None] * page_count
            realized_pages: List[FreeformPageBlueprint | None] = [None] * page_count
            for idx, page_brief in enumerate(page_briefs):
                restored = restored_pages.get(str(page_brief.page_id or "").strip())
                if restored is not None:
                    ordered_results[idx] = restored
                    realized_pages[idx] = restored[0]

            async def _run_page(idx: int, page_brief: PageBrief) -> None:
                if ordered_results[idx] is not None:
                    return
                if execution_session is not None:
                    execution_session.raise_if_cancelled()
                page_label = self._legacy_helper._progress_page_label(page_brief, idx + 1)
                await self._emit_progress(
                    progress_callback,
                    {
                        "stage": "image_native_page_generation",
                        "status": "running",
                        "kind": "write",
                        "page_index": idx + 1,
                        "page_total": page_count,
                        "page_id": str(page_brief.page_id or "").strip(),
                        "page_label": page_label,
                        "message": f"正在用 image-native 路线生成第{idx + 1}页：{page_label}",
                    },
                )
                prior_pages = [page for page in realized_pages[:idx] if page is not None]
                async with sem:
                    page, artifact = await self._build_one_page(
                        deck_brief=deck_brief,
                        constraint_bundle=constraint_bundle,
                        page_brief=page_brief,
                        built_pages=prior_pages,
                        user_id=user_id,
                        session_id=session_id,
                    )
                realized_pages[idx] = page
                ordered_results[idx] = (page, artifact)
                if execution_session is not None:
                    await execution_session.checkpoint_page(
                        str(page_brief.page_id or "").strip(),
                        page.model_dump(),
                        metadata=artifact,
                    )
                logger.info(
                    "presentation_image_native_page_ready page_id=%s block_count=%s page_index=%s",
                    str(page.page_id or "").strip(),
                    len(list(page.blocks or [])),
                    idx + 1,
                )

            await asyncio.gather(*[_run_page(idx, page_brief) for idx, page_brief in enumerate(page_briefs)])

            for item in ordered_results:
                if item is None:
                    continue
                page, artifact = item
                built_pages.append(page)
                page_artifacts.append(artifact)
                repair_reports.append(self._repair_report(page))

        blueprint = FreeformDeckBlueprint(
            deck_id=str(deck_brief.deck_id or story_plan.deck_id or "presentation").strip() or "presentation",
            deck_goal=str(deck_brief.deck_goal or story_plan.deck_goal or "").strip(),
            target_audience=str(deck_brief.target_audience or story_plan.target_audience or "").strip(),
            theme=build_freeform_theme_from_design_tokens(deck_brief.design_tokens),
            pages=built_pages,
        )
        blueprint.runtime = {
            "source": "presentation_image_native_rebuild",
            "story_outline": json.dumps(self._legacy_helper._story_payload(story_plan=story_plan), ensure_ascii=False),
            "deck_brief": deck_brief.model_dump(),
            "constraint_bundle": constraint_bundle.model_dump(),
            "repair_reports": [report.model_dump() for report in repair_reports],
            "image_native_artifacts": page_artifacts,
        }
        return self._legacy_helper._renumber_pages(blueprint)

    @staticmethod
    def _repair_report(page: FreeformPageBlueprint) -> PageRepairReport:
        return PageRepairReport(
            page_id=page.page_id,
            issues=[],
            accepted=True,
            attempt_count=1,
            issue_score_before=0,
            issue_score_after=0,
        )

    @staticmethod
    def _page_concurrency(page_count: int) -> int:
        configured = int(get_settings().PRESENTATION_IMAGE_NATIVE_PAGE_CONCURRENCY or 1)
        return max(1, min(max(1, page_count), configured))

    async def _build_one_page(
        self,
        *,
        deck_brief: DeckBrief,
        constraint_bundle: ConstraintBundle,
        page_brief: PageBrief,
        built_pages: List[FreeformPageBlueprint],
        user_id: str,
        session_id: str,
    ) -> tuple[FreeformPageBlueprint, Dict[str, Any]]:
        deck_creative = self._brief_compiler.compile_deck_creative_brief(
            deck_brief,
            constraint_bundle,
        )
        page_idx = 0
        for candidate_idx, candidate in enumerate(list(deck_brief.page_briefs or [])):
            if str(candidate.page_id or "").strip() == str(page_brief.page_id or "").strip():
                page_idx = candidate_idx
                break
        previous = deck_brief.page_briefs[page_idx - 1] if page_idx > 0 and deck_brief.page_briefs else None
        next_page = None
        if deck_brief.page_briefs and page_idx + 1 < len(deck_brief.page_briefs):
            next_page = deck_brief.page_briefs[page_idx + 1]
        page_creative = self._brief_compiler.compile_page_creative_brief(
            page_brief=page_brief,
            previous_page=previous,
            next_page=next_page,
            prior_pages=built_pages,
            bundle=constraint_bundle,
        )
        theme_reference = self._legacy_helper._theme_reference_markdown(str(deck_brief.theme_factory_name or "").strip())
        page_session_id = f"{session_id}::{str(page_brief.page_id or '').strip() or f'page_{page_idx + 1:02d}'}"

        page_plan_payload = await self._responses.call_json(
            prompt=build_page_plan_prompt(
                deck_brief=deck_brief,
                page_brief=page_brief,
                deck_creative_brief=deck_creative,
                page_creative_brief=page_creative,
                theme_reference=theme_reference,
            ),
            stage="presentation_image_native_page_plan",
            intent="generation",
            user_id=user_id,
            session_id=page_session_id,
            request_payload_extra={"page_id": str(page_brief.page_id or "")},
        )
        page_plan = ImageNativePagePlan.model_validate(page_plan_payload)
        page_plan.page_id = str(page_plan.page_id or page_brief.page_id).strip() or str(page_brief.page_id).strip()
        page_plan.page_index = int(page_plan.page_index or page_brief.page_index or 0)
        page_plan.full_slide_prompt = constrain_full_slide_prompt(page_plan.full_slide_prompt)
        page_plan_dict = page_plan.model_dump()

        generated = await self._slide_generator.generate(
            prompt=page_plan.full_slide_prompt,
            user_id=user_id,
            page_id=str(page_plan.page_id or "page"),
            log_context={"page_id": page_plan.page_id, "stage": "full_slide"},
        )
        analysis = await self._visual_analyzer.analyze(
            page_plan=page_plan_dict,
            image_bytes=bytes(generated["bytes"]),
            user_id=user_id,
            session_id=page_session_id,
        )
        analysis_dict = analysis.model_dump()
        asset_map = await self._asset_generator.generate_assets(
            analysis=analysis_dict,
            user_id=user_id,
            page_id=page_plan.page_id,
        )
        icon_svg_map = await self._icon_generator.generate_icons(
            analysis=analysis_dict,
            user_id=user_id,
            session_id=page_session_id,
            page_id=page_plan.page_id,
        )
        try:
            page = await self._blueprint_composer.compose(
                deck_brief=deck_brief.model_dump(),
                page_plan=page_plan_dict,
                visual_analysis=analysis_dict,
                image_asset_map=asset_map,
                icon_svg_map=icon_svg_map,
                source_slide_image_url=str(generated.get("url") or ""),
                user_id=user_id,
                session_id=page_session_id,
            )
        except Exception:
            logger.warning(
                "presentation_image_native_blueprint_compose_failed page_id=%s",
                page_plan.page_id,
                exc_info=True,
            )
            page = fallback_page_from_analysis(
                page_plan=page_plan_dict,
                analysis=analysis_dict,
                image_asset_map=asset_map,
                icon_svg_map=icon_svg_map,
                source_slide_image_url=str(generated.get("url") or ""),
            )
        page = postprocess_image_native_page(
            page,
            source_slide_image_url=str(generated.get("url") or ""),
            image_asset_map=asset_map,
            allow_source_slide_background=_allows_source_slide_background(page_plan_dict),
        )

        artifact = {
            "page_id": page.page_id,
            "full_slide_image_url": str(generated.get("url") or ""),
            "full_slide_image_object_path": str(generated.get("object_path") or ""),
            "full_slide_prompt": page_plan.full_slide_prompt,
            "page_plan": page_plan_dict,
            "visual_analysis": analysis_dict,
            "image_asset_map": asset_map,
            "icon_svg_map": icon_svg_map,
        }
        return page, artifact


def _allows_source_slide_background(page_plan: Dict[str, Any]) -> bool:
    page_type = str((page_plan or {}).get("page_type") or "").strip().lower()
    return page_type in {"cover", "closing", "thank_you", "thankyou", "back_cover"}
