"""Thin DSH adapter over MOVO's durable, editable presentation pipeline."""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from app.enterprise_capabilities.runtime.contracts import CapabilityExecutionContext
from app.llm.configured_models import (
    ModelConfigError,
    get_default_model_config,
    get_model_config,
    get_model_config_by_capability,
    reset_configured_model_context,
    set_configured_model_context,
)
from app.llm.configured_image_models import get_image_model_config
from app.infrastructure.request_context import reset_request_context, set_request_context
from app.services.presentation.pipeline_selector import build_presentation_pipeline
from app.services.presentation.settings import get_presentation_generation_settings
from app.services.conversation_evidence_service import (
    ConversationEvidenceUnavailable,
    conversation_evidence_service,
)

from .contracts import normalize_presentation_arguments
from .evidence import presentation_tool_observations
from .progress import PresentationTimelineProjector
from .job_coordinator import PresentationJobCoordinator


class PresentationCreationCapability:
    """Own the internal Blueprint; expose only a business brief to DSH."""

    def __init__(
        self,
        pipeline_factory: Callable[[dict[str, Any]], Any] = build_presentation_pipeline,
        job_coordinator: PresentationJobCoordinator | None = None,
    ) -> None:
        self._pipeline_factory = pipeline_factory
        self._job_coordinator = (
            job_coordinator
            if job_coordinator is not None
            else (PresentationJobCoordinator() if pipeline_factory is build_presentation_pipeline else None)
        )

    async def run(
        self,
        arguments: dict[str, Any],
        context: CapabilityExecutionContext,
    ) -> dict[str, Any]:
        args = normalize_presentation_arguments(arguments)
        if not args["request"]:
            return self._rejected("presentation request is empty", requested=args["page_count"])
        presentation_settings = await get_presentation_generation_settings(context.tenant_id)
        generation_mode = str((presentation_settings or {}).get("generation_mode") or "llm")
        if generation_mode not in {"llm", "image_rebuild"}:
            return self._rejected("PPT generation mode is invalid; update it in admin settings", requested=args["page_count"])
        model_config = await self._model_config(context, presentation_settings)
        if model_config is None:
            return self._rejected("PPT content model is unavailable; update it in admin settings", requested=args["page_count"])
        image_model_config = None
        vision_model_config = None
        if generation_mode == "image_rebuild":
            image_model_config = await self._image_model_config(context, presentation_settings)
            if image_model_config is None:
                return self._rejected(
                    "PPT image generation model is unavailable; update it in admin settings",
                    requested=args["page_count"],
                )
            vision_model_config = await self._vision_model_config(context, presentation_settings)
            if vision_model_config is None:
                return self._rejected(
                    "PPT vision rebuild model is unavailable; update it in admin settings",
                    requested=args["page_count"],
                )

        request_context = {
            "main_id": context.tenant_id,
            "user_id": context.user_id,
            "configured_model": model_config,
            "model_instance_id": context.model_instance_id,
        }
        if vision_model_config:
            request_context["vision_model_config"] = vision_model_config
        if image_model_config:
            request_context["image_model_id"] = str(image_model_config.get("id") or "")
        previous_request = set_request_context(request_context)
        previous_model = set_configured_model_context(model_config)
        try:
            resolved_context = await self._with_conversation_evidence(args, context)
            return await self._run_pipeline(args, resolved_context, generation_mode=generation_mode)
        finally:
            reset_configured_model_context(previous_model)
            reset_request_context(previous_request)

    @staticmethod
    async def _with_conversation_evidence(
        args: dict[str, Any],
        context: CapabilityExecutionContext,
    ) -> CapabilityExecutionContext:
        if not args["use_conversation_evidence"]:
            return context
        existing = context.turn_context.get("evidence_bundle")
        if isinstance(existing, dict) and existing:
            return context
        try:
            resolved = await conversation_evidence_service.collect(
                session_id=context.conversation_id,
                user_id=context.user_id,
                main_id=context.tenant_id,
                current_request=str(
                    context.turn_context.get("user_request") or args["request"]
                ),
                evidence_requirement=args["request"],
            )
        except ConversationEvidenceUnavailable:
            return context
        bundle = resolved.get("evidence_bundle")
        if not isinstance(bundle, dict) or not bundle:
            return context
        return context.model_copy(update={
            "turn_context": {**context.turn_context, "evidence_bundle": bundle},
        })

    async def _run_pipeline(
        self,
        args: dict[str, Any],
        context: CapabilityExecutionContext,
        *,
        generation_mode: str,
    ) -> dict[str, Any]:
        output_spec = self._output_spec(args, context, generation_mode=generation_mode)
        execution_session = None
        if self._job_coordinator is not None:
            opened = await self._job_coordinator.open(
                arguments=args,
                context=context,
                generation_mode=generation_mode,
            )
            if opened.terminal_result is not None:
                return opened.terminal_result
            execution_session = opened.session
        projector = PresentationTimelineProjector(
            action_id=context.action_id,
            message_id=context.message_id,
        )

        async def publish_progress(payload: dict[str, Any]) -> None:
            row = projector.project(payload)
            if row is not None:
                await context.publish_progress(row)

        try:
            build_arguments: dict[str, Any] = {
                "messages": [{"role": "user", "content": self._pipeline_request(args, context)}],
                "output_spec": output_spec,
                "progress_callback": publish_progress,
            }
            if execution_session is not None:
                build_arguments["execution_session"] = execution_session
            result = await self._pipeline_factory(output_spec).build(**build_arguments)
        except asyncio.CancelledError:
            if execution_session is not None and self._job_coordinator is not None:
                await asyncio.shield(
                    self._job_coordinator.interrupt(execution_session, "presentation execution interrupted")
                )
            raise
        except Exception as exc:
            if execution_session is not None and self._job_coordinator is not None:
                await self._job_coordinator.fail(execution_session, str(exc))
            raise
        bundle = self._dict(result.get("preview_bundle"))
        document = self._dict(result.get("document_payload"))
        slide_count = int(bundle.get("slide_count") or 0)
        blueprint = self._dict(bundle.get("deck_ir_artifact"))
        html_preview = self._dict(bundle.get("html_preview"))
        reasons: list[str] = []
        if slide_count <= 0:
            reasons.append("presentation_has_no_slides")
        if args["page_count"] and slide_count != args["page_count"]:
            reasons.append("requested_slide_count_mismatch")
        if not str(blueprint.get("object_path") or "").strip():
            reasons.append("editable_blueprint_missing")
        if not str(html_preview.get("object_path") or "").strip():
            reasons.append("html_preview_missing")
        if reasons:
            if execution_session is not None and self._job_coordinator is not None:
                await self._job_coordinator.interrupt(execution_session, ", ".join(reasons))
            return self._rejected(
                ", ".join(reasons),
                requested=args["page_count"],
                slide_count=slide_count,
                reasons=reasons,
            )

        artifact = self._stable_document(document)
        story_plan = result.get("story_plan")
        deck_goal = str(getattr(story_plan, "deck_goal", "") or artifact.get("title") or "PPT").strip()
        artifact.update({
            "type": "presentation_preview_bundle",
            "title": deck_goal,
            "lifecycle": "final",
            "visibility": "user",
            "delivery_id": f"presentation:{context.action_id}",
        })
        acceptance = {
            "status": "accepted",
            "retry_allowed": False,
            "reasons": [],
            "slide_count": slide_count,
            "requested_slide_count": int(args["page_count"]),
            "editable": True,
        }
        capability_result = {
            "success": True,
            "accepted": True,
            "acceptance": acceptance,
            "artifact": artifact,
            "message": "",
        }
        if execution_session is not None and self._job_coordinator is not None:
            await self._job_coordinator.complete(execution_session, capability_result)
        return capability_result

    @staticmethod
    def _pipeline_request(args: dict[str, Any], context: CapabilityExecutionContext) -> str:
        request = str(args["request"])
        count = int(args["page_count"])
        if not count:
            return request
        language = str(context.turn_context.get("language") or "zh").lower()
        contract = (
            f"MOVO 交付合同：必须生成且仅生成 {count} 页幻灯片。"
            if language.startswith("zh")
            else f"MOVO delivery contract: produce exactly {count} slides."
        )
        return f"{request}\n\n{contract}"

    @staticmethod
    def _output_spec(
        args: dict[str, Any],
        context: CapabilityExecutionContext,
        *,
        generation_mode: str,
    ) -> dict[str, Any]:
        sections = list(args["required_sections"])
        section_specs = [
            {"title": title, "order": index}
            for index, title in enumerate(sections, start=1)
        ]
        return {
            "user_id": context.user_id,
            "main_id": context.tenant_id,
            "request_id": context.action_id,
            "task_id": context.action_id,
            "language": str(context.turn_context.get("language") or "zh"),
            "target_audience": args["audience"],
            "presentation_context": args["request"],
            "presentation_generation_mode": generation_mode,
            "use_agenda": args["use_agenda"],
            "grounding_strictness": args["grounding_mode"],
            "tool_observations": presentation_tool_observations(context.turn_context),
            "compose_policy": {
                "audience": args["audience"],
                "content_form": "presentation",
                "required_sections": sections,
                "presentation_policy": {"design_intent": args["design_intent"]},
            },
            "content_task_spec": {
                "execution_kind": "presentation",
                "audience": {"primary": args["audience"]},
                "goal": {"outcome": args["request"], "primary_action": "create_presentation"},
                "schema": {"category": "presentation", "section_specs": section_specs},
            },
        }

    @staticmethod
    def _dict(value: Any) -> dict[str, Any]:
        if hasattr(value, "model_dump"):
            return dict(value.model_dump())
        return dict(value or {}) if isinstance(value, dict) else {}

    @classmethod
    def _stable_document(cls, document: dict[str, Any]) -> dict[str, Any]:
        """Return the small, durable artifact descriptor DSH and the UI need.

        The preview builder persists the full editable deck IR as JSON. Returning
        the same IR again inside the tool result can exceed DSH's tool-result
        budget; DSH then replaces the value with truncation metadata which no
        longer matches this capability's output schema. Keep only stable object
        references here. The frontend already loads the Blueprint from
        ``deck_ir_artifact.object_path`` when the editor opens.
        """

        bundle = cls._dict(document.get("bundle"))
        html_preview = cls._artifact_ref(bundle.get("html_preview"))
        deck_ir_artifact = cls._artifact_ref(bundle.get("deck_ir_artifact"))
        raw_metadata = cls._dict(bundle.get("preview_metadata"))
        blueprint_path = str(
            raw_metadata.get("blueprint_artifact_path")
            or deck_ir_artifact.get("object_path")
            or ""
        ).strip()
        compact_metadata = {
            "blueprint_artifact_path": blueprint_path,
            "delivery_mode": str(raw_metadata.get("delivery_mode") or "artifact_preview").strip(),
            "preview_upload_failed": bool(raw_metadata.get("preview_upload_failed")),
        }
        compact_bundle = {
            "artifact_version": str(bundle.get("artifact_version") or "0.1"),
            "pipeline_version": str(bundle.get("pipeline_version") or "current"),
            "slide_count": int(bundle.get("slide_count") or 0),
            "html_preview": html_preview,
            "deck_ir_artifact": deck_ir_artifact,
            "preview_metadata": compact_metadata,
        }
        return {
            "type": str(document.get("type") or "presentation_preview_bundle"),
            "object_path": str(document.get("object_path") or html_preview.get("object_path") or "").strip(),
            "filename": str(document.get("filename") or html_preview.get("filename") or "").strip(),
            "title": str(document.get("title") or "PPT HTML 预览").strip(),
            "bundle": compact_bundle,
            "summary": cls._dict(document.get("summary")),
        }

    @classmethod
    def _artifact_ref(cls, value: Any) -> dict[str, str]:
        source = cls._dict(value)
        return {
            "object_path": str(source.get("object_path") or "").strip(),
            "filename": str(source.get("filename") or "").strip(),
        }

    @staticmethod
    def _rejected(
        message: str,
        *,
        requested: int,
        slide_count: int = 0,
        reasons: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "success": False,
            "accepted": False,
            "acceptance": {
                "status": "rejected",
                "retry_allowed": True,
                "reasons": list(reasons or [message]),
                "slide_count": int(slide_count),
                "requested_slide_count": int(requested),
                "editable": False,
            },
            "message": message,
        }

    @staticmethod
    async def _model_config(
        context: CapabilityExecutionContext,
        settings: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        configured_id = str((settings or {}).get("llm_model_id") or "").strip()
        try:
            if configured_id:
                return await get_model_config_by_capability(
                    configured_id,
                    context.tenant_id,
                    capability="chat",
                )
            model = None
            if context.model_instance_id:
                model = await get_model_config(context.model_instance_id, context.tenant_id)
            return model or await get_default_model_config(context.tenant_id)
        except ModelConfigError:
            return None

    @staticmethod
    async def _image_model_config(
        context: CapabilityExecutionContext,
        settings: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        model_id = str((settings or {}).get("image_model_id") or "").strip()
        if not model_id:
            return None
        try:
            return await get_image_model_config(model_id, context.tenant_id)
        except ModelConfigError:
            return None

    @staticmethod
    async def _vision_model_config(
        context: CapabilityExecutionContext,
        settings: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        model_id = str((settings or {}).get("vision_model_id") or "").strip()
        if not model_id:
            return None
        try:
            return await get_model_config_by_capability(
                model_id,
                context.tenant_id,
                capability="vision",
            )
        except ModelConfigError:
            return None


_capability = PresentationCreationCapability()


async def presentation_create(
    arguments: dict[str, Any],
    context: CapabilityExecutionContext,
) -> dict[str, Any]:
    return await _capability.run(arguments, context)


__all__ = ["PresentationCreationCapability", "presentation_create"]
