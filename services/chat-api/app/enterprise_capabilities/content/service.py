from __future__ import annotations

import re
from typing import Any, Callable

from app.enterprise_capabilities.runtime.contracts import CapabilityExecutionContext
from app.llm.configured_models import (
    get_default_model_config,
    get_model_config,
    reset_configured_model_context,
    set_configured_model_context,
)
from app.infrastructure.request_context import reset_request_context, set_request_context
from app.enterprise_capabilities.content.writer_engine.compose_skill import ToolWriterEngineComposeSkill

from .contracts import normalized_content_arguments
from .evidence import resolve_content_evidence
from .profile import apply_content_profile
from .routing import ContentWriterRouter
from .styles import WritingStyleResolver
from .timeline import ContentTimelineProjector
from .visuals import FinalBodyVisualAssembler
from .quality import ExistingContentQualityClosure
from .acceptance import build_content_acceptance
from .writer_runner import ContentWriterRunner
from .progress import ContentProgressReporter


_MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\([^\)]+\)")


class ContentProductionService:
    """Thin DSH adapter over ASKAI's tested writer engine."""

    def __init__(
        self,
        *,
        writer_factory: Callable[[], Any] = ToolWriterEngineComposeSkill,
        style_resolver: WritingStyleResolver | None = None,
        profile_applier: Callable[..., Any] = apply_content_profile,
        visual_assembler: FinalBodyVisualAssembler | None = None,
        writer_router: ContentWriterRouter | None = None,
        quality_closure: ExistingContentQualityClosure | None = None,
    ) -> None:
        self._writer_factory = writer_factory
        self._styles = style_resolver or WritingStyleResolver()
        self._apply_profile = profile_applier
        self._visuals = visual_assembler or FinalBodyVisualAssembler()
        self._writer_router = writer_router or ContentWriterRouter()
        self._quality = quality_closure or ExistingContentQualityClosure()

    async def run(self, arguments: dict[str, Any], context: CapabilityExecutionContext) -> dict[str, Any]:
        args = normalized_content_arguments(arguments)
        if not args["request"]:
            return {"success": False, "message": "content request is empty"}
        model_config = await self._model_config(context)
        if model_config is None:
            return {"success": False, "message": "content production model is unavailable"}

        previous_request = set_request_context({
            "main_id": context.tenant_id,
            "user_id": context.user_id,
            "configured_model": model_config,
            "model_instance_id": context.model_instance_id,
        })
        previous_model = set_configured_model_context(model_config)
        try:
            return await self._run_pipeline(args, context)
        finally:
            reset_configured_model_context(previous_model)
            reset_request_context(previous_request)

    async def _run_pipeline(self, args: dict[str, Any], context: CapabilityExecutionContext) -> dict[str, Any]:
        projector = ContentTimelineProjector(
            outer_action_id=context.action_id, message_id=context.message_id,
        )
        progress = ContentProgressReporter(
            projector=projector,
            sink=context.publish_progress,
            language=str(context.turn_context.get("language") or "zh"),
        )
        await progress.emit("requirements")
        selected_id = str(context.turn_context.get("selected_writing_skill_id") or "").strip()
        selected_styles, style_contract = await self._styles.resolve(
            request=args["request"], tenant_id=context.tenant_id, user_id=context.user_id,
            selected_skill_id=selected_id,
        )
        task_ir = {
            "execution_class": "content_generation",
            "goal": {"outcome": args["request"], "primary_action": f"compose_{args['content_form']}"},
            "constraints": {"writing_mode": args["writing_mode"]},
        }
        output_spec = self._output_spec(args, context, task_ir, selected_styles, style_contract)
        await progress.emit("planning")
        profile_meta = await self._apply_profile(
            messages=[{"role": "user", "content": args["request"]}],
            output_spec=output_spec,
            task_ir=task_ir,
        )
        writer_route = self._writer_router.apply(output_spec=output_spec, user_query=args["request"])
        await progress.emit(
            "sectional" if str(writer_route.get("mode") or "") == "sectional_compose" else "direct"
        )
        evidence_bundle = resolve_content_evidence(context.turn_context)
        writer_payload = {
            "preserve_activity_events": True,
            "writer_style_contract": style_contract,
            "writer_style_contract_block": str(style_contract.get("prompt_block") or ""),
            "selected_style_skills": selected_styles,
            "selected_style_markdowns": [],
            "evidence_bundle": evidence_bundle,
        }
        runner = ContentWriterRunner(self._writer_factory)
        first_run = await runner.run(
            request=args["request"], output_spec=output_spec, payload=writer_payload,
            projector=projector, publish_progress=context.publish_progress,
        )
        artifacts = list(first_run.artifacts)

        async def publish_native(event: dict[str, Any]) -> None:
            for row in projector.project(event):
                await context.publish_progress(row)

        async def regenerate(feedback: str) -> str:
            retry_run = await runner.run(
                request=args["request"], output_spec=output_spec, payload=writer_payload,
                projector=projector, publish_progress=context.publish_progress,
                feedback=feedback,
            )
            artifacts.extend(retry_run.artifacts)
            return retry_run.markdown

        quality_result = await self._quality.close(
            user_request=args["request"],
            markdown=first_run.markdown,
            writer_path=first_run.writer_path,
            skill_context=self._quality_skill_context(
                output_spec=output_spec,
                style_contract=style_contract,
            ),
            regenerate=regenerate,
            progress_sink=publish_native,
            language=str(output_spec.get("language") or "zh"),
        )
        markdown = quality_result.markdown
        async def publish_visual_progress(event: dict[str, Any]) -> None:
            for row in projector.project(event):
                await context.publish_progress(row)

        visual_result = await self._visuals.finalize(
            markdown=markdown,
            output_spec=output_spec,
            user_query=args["request"],
            language=str(output_spec.get("language") or "zh"),
            user_id=context.user_id,
            progress_sink=publish_visual_progress,
        )
        markdown = visual_result.markdown
        image_count = len(_MARKDOWN_IMAGE.findall(markdown))
        acceptance = build_content_acceptance(
            markdown=markdown,
            image_count=image_count,
            required_visual_min=int(args["visual_min"]),
            quality_verdict=quality_result.verdict,
            quality_status=quality_result.evaluation_status,
        )
        success = acceptance["status"] == "accepted"
        return {
            "success": success,
            "accepted": success,
            "acceptance": acceptance,
            "markdown": markdown,
            "artifacts": artifacts,
            "production": {
                **dict(profile_meta or {}),
                "selected_style_names": [str(item.get("name") or "") for item in selected_styles],
                "character_count": len(markdown),
                "image_count": image_count,
                "required_visual_min": int(args["visual_min"]),
                "visual_assets": list(visual_result.assets),
                "visual_assembly": dict(visual_result.assembly),
                "writer_route": writer_route,
                "evidence_count": len(list(evidence_bundle.get("results") or [])),
                "quality": {
                    "verdict": quality_result.verdict,
                    "evaluation_status": quality_result.evaluation_status,
                    "standards_count": quality_result.standards_count,
                    "issues_count": quality_result.issues_count,
                    "repair_applied": quality_result.repair_applied,
                    "metadata": dict(quality_result.metadata),
                },
                "recovered_contract_fields": list(
                    context.turn_context.get("content_contract_recovered_fields") or []
                ),
            },
            "message": "" if success else (
                "required visuals were not generated"
                if "required_visuals_missing" in acceptance["reasons"]
                else "content pipeline returned no content"
            ),
        }

    @staticmethod
    def _quality_skill_context(
        *,
        output_spec: dict[str, Any],
        style_contract: dict[str, Any],
    ) -> dict[str, Any]:
        preset = output_spec.get("profile_preset") if isinstance(output_spec.get("profile_preset"), dict) else {}
        return {
            "writer_style_contract": dict(style_contract or {}),
            "profile_preset": {
                "source": str(preset.get("source") or ""),
                "preset_id": str(preset.get("preset_id") or preset.get("id") or ""),
                "compose_policy": dict(preset.get("compose_policy") or {}),
                "structure_contract": dict(preset.get("structure_contract") or {}),
                "quality_gates": dict(preset.get("quality_gates") or {}),
            },
            "resolved_required_blocks": list(output_spec.get("required_blocks") or []),
        }

    @staticmethod
    def _output_spec(
        args: dict[str, Any],
        context: CapabilityExecutionContext,
        task_ir: dict[str, Any],
        selected_styles: list[dict[str, Any]],
        style_contract: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "user_id": context.user_id,
            "main_id": context.tenant_id,
            "request_id": context.action_id,
            "language": str(context.turn_context.get("language") or "zh"),
            "required_blocks": list(args["required_sections"]),
            "selected_style_skills": selected_styles,
            "manual_selected_style_skill": selected_styles[0] if selected_styles else {},
            "manual_skill_selected": bool(selected_styles),
            "writing_skill_source": "manual_selected" if selected_styles else "dynamic_preset",
            "writer_style_contract": style_contract,
            "writer_style_contract_block": str(style_contract.get("prompt_block") or ""),
            "compose_policy": {
                "content_form": args["content_form"], "audience": args["audience"], "tone": args["tone"],
            },
            "generation_policy": {"min_words": args["min_words"], "max_words": args["max_words"]},
            "content_task_spec": {
                "execution_kind": "content",
                "writing_mode": args["writing_mode"],
                "schema": {"category": args["content_form"], "type": args["content_form"]},
                "goal": dict(task_ir["goal"]),
                "audience": {"primary": args["audience"]},
                "visual_plan": {"min_assets": args["visual_min"], "max_assets": args["visual_max"]},
            },
            "task_ir": task_ir,
        }

    @staticmethod
    async def _model_config(context: CapabilityExecutionContext) -> dict[str, Any] | None:
        model = None
        if context.model_instance_id:
            model = await get_model_config(context.model_instance_id, context.tenant_id)
        return model or await get_default_model_config(context.tenant_id)


_default_service = ContentProductionService()


async def content_production(arguments: dict[str, Any], context: CapabilityExecutionContext) -> dict[str, Any]:
    return await _default_service.run(arguments, context)


__all__ = ["ContentProductionService", "content_production"]
