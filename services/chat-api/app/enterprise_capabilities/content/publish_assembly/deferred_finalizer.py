from __future__ import annotations

import json
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from app.llm.factory import get_request_scoped_llm_client
from app.llm.types import Message, Role
from app.llm.decision_turn import DecisionOutput, DecisionTurnSpec, invoke_structured_decision
from app.enterprise_capabilities.content.planning.contracts import ContentPlanSpec, PlanSectionSpec, VisualSlotSpec
from app.enterprise_capabilities.content.publish_assembly.assembler import PublishAssembler
from app.enterprise_capabilities.content.publish_assembly.contracts import PublishAssemblySpec
from app.enterprise_capabilities.content.publish_assembly.section_locator import locate_final_body_sections


class _FinalVisualSlot(BaseModel):
    role: str = ""
    anchor_section_index: int = 0
    description: str = ""


class _FinalVisualPlan(DecisionOutput):
    slots: List[_FinalVisualSlot] = Field(default_factory=list)


class DeferredVisualFinalizer:
    """Plan and materialize generated visuals only after the final body is accepted."""

    def __init__(self) -> None:
        self._llm = get_request_scoped_llm_client(streaming=False, stage="visual_planning", intent="task")
        self._assembler = PublishAssembler()

    def has_visual_work(self, *, final_markdown: str, output_spec: Dict[str, Any]) -> bool:
        body = str(final_markdown or "").strip()
        if not body or bool(output_spec.get("deferred_visuals_disabled")):
            return False
        sections = self._sections_from_final_markdown(body)
        _, maximum = self._visual_bounds(output_spec=output_spec, section_count=len(sections))
        return maximum > 0

    async def finalize(
        self,
        *,
        final_markdown: str,
        output_spec: Dict[str, Any],
        user_query: str,
        language: str,
        user_id: str,
    ) -> PublishAssemblySpec:
        body = str(final_markdown or "").strip()
        if not body:
            return PublishAssemblySpec()
        if bool(output_spec.get("deferred_visuals_disabled")):
            return PublishAssemblySpec(body_markdown=body, final_markdown=body)

        sections = self._sections_from_final_markdown(body)
        minimum, maximum = self._visual_bounds(output_spec=output_spec, section_count=len(sections))
        if maximum <= 0:
            return PublishAssemblySpec(body_markdown=body, final_markdown=body)

        slots = await self._plan_slots(
            body=body,
            sections=sections,
            output_spec=output_spec,
            user_query=user_query,
            minimum=minimum,
            maximum=maximum,
            language=language,
        )
        if not slots:
            return PublishAssemblySpec(body_markdown=body, final_markdown=body)

        plan = ContentPlanSpec(
            plan_id="final_body_visual_plan",
            sections=sections,
            visual_slots=slots,
            metadata={"source": "post_quality_final_body"},
        )
        return await self._assembler.assemble(
            body_markdown=body,
            content_plan=plan.model_dump(),
            user_query=user_query,
            language=language,
            user_id=user_id,
            output_spec=output_spec,
        )

    @staticmethod
    def _sections_from_final_markdown(markdown: str) -> List[PlanSectionSpec]:
        sections = locate_final_body_sections(markdown)
        if not sections:
            return [PlanSectionSpec(section_id="final_s1", title="正文", purpose=str(markdown or "")[:500])]
        return [
            PlanSectionSpec(
                section_id=section.section_id,
                title=section.title,
                purpose=section.purpose,
            )
            for section in sections[:24]
        ]

    @staticmethod
    def _visual_bounds(*, output_spec: Dict[str, Any], section_count: int) -> tuple[int, int]:
        content_task_spec = output_spec.get("content_task_spec") if isinstance(output_spec.get("content_task_spec"), dict) else {}
        visual_plan = content_task_spec.get("visual_plan") if isinstance(content_task_spec.get("visual_plan"), dict) else {}
        old_content_plan = output_spec.get("content_plan") if isinstance(output_spec.get("content_plan"), dict) else {}
        old_slots = [item for item in list(old_content_plan.get("visual_slots") or []) if isinstance(item, dict)]
        minimum = max(0, int(visual_plan.get("min_assets") or 0))
        maximum = max(minimum, int(visual_plan.get("max_assets") or 0))
        explicit_visual_intent = bool(visual_plan.get("required") or list(visual_plan.get("assets") or []))
        adaptive_maximum = max(1, min(8, (max(1, int(section_count or 1)) + 1) // 2))

        if maximum > 0:
            capped_maximum = min(8, maximum)
            capped_minimum = min(capped_maximum, minimum if minimum > 0 else (1 if explicit_visual_intent else 0))
            return (capped_minimum, capped_maximum)
        if explicit_visual_intent:
            return (1, adaptive_maximum)
        if old_slots:
            # Old slots only preserve the previous decision that automatic visuals
            # were useful. Their anchors, descriptions, and prompts are discarded.
            return (0, min(adaptive_maximum, len(old_slots)))
        return (0, 0)

    async def _plan_slots(
        self,
        *,
        body: str,
        sections: List[PlanSectionSpec],
        output_spec: Dict[str, Any],
        user_query: str,
        minimum: int,
        maximum: int,
        language: str,
    ) -> List[VisualSlotSpec]:
        content_task_spec = output_spec.get("content_task_spec") if isinstance(output_spec.get("content_task_spec"), dict) else {}
        visual_plan = content_task_spec.get("visual_plan") if isinstance(content_task_spec.get("visual_plan"), dict) else {}
        payload = {
            "user_request": str(user_query or "")[:1600],
            "visual_requirements": [dict(item) for item in list(visual_plan.get("assets") or []) if isinstance(item, dict)][:8],
            "minimum_images": minimum,
            "maximum_images": maximum,
            "language": language,
            "final_sections": [
                {"index": idx, "title": sec.title, "content_excerpt": sec.purpose}
                for idx, sec in enumerate(sections)
            ],
            "final_body_excerpt": body[:8000],
        }
        system = (
            "Plan image slots from the FINAL accepted article body. Return structured output only.\n"
            "Every slot must be grounded in the final body, not in an earlier outline or draft.\n"
            "Use between minimum_images and maximum_images slots. If minimum_images is zero, use fewer or no slots when visuals add no value.\n"
            "anchor_section_index is zero-based and must reference final_sections.\n"
            "description must be a concrete image-generation brief naming the actual subject, relationships, context, and suitable visual form.\n"
            "Do not use vague descriptions such as relevant image, article illustration, visual requirement, or summary image.\n"
            "Prefer diagrams, comparisons, mechanisms, processes, timelines, or concrete scenes that improve understanding.\n"
            "Do not invent facts, entities, industries, or scenarios absent from the final body.\n"
        )
        try:
            parsed = await invoke_structured_decision(
                self._llm,
                _FinalVisualPlan,
                [
                    Message(role=Role.SYSTEM, content=system),
                    Message(role=Role.USER, content=json.dumps(payload, ensure_ascii=False, default=str)),
                ],
                spec=DecisionTurnSpec(locale=language, turn_id="visual.final_plan"),
            )
        except Exception:
            return self._fallback_slots(sections=sections, count=minimum, language=language)
        if not isinstance(parsed, _FinalVisualPlan):
            return self._fallback_slots(sections=sections, count=minimum, language=language)

        planned: List[VisualSlotSpec] = []
        for item in list(parsed.slots or [])[:maximum]:
            description = str(item.description or "").strip()
            if not description:
                continue
            anchor_index = max(0, min(len(sections) - 1, int(item.anchor_section_index or 0)))
            planned.append(
                VisualSlotSpec(
                    slot_id=f"final_v{len(planned) + 1}",
                    role=str(item.role or "illustration").strip() or "illustration",
                    anchor_section_id=sections[anchor_index].section_id,
                    description=description[:500],
                )
            )
        if len(planned) < minimum:
            used_anchors = {str(item.anchor_section_id or "") for item in planned}
            supplements = self._fallback_slots(
                sections=sections,
                count=minimum - len(planned),
                language=language,
                excluded_section_ids=used_anchors,
                slot_offset=len(planned),
            )
            planned.extend(supplements)
        return planned

    @staticmethod
    def _fallback_slots(
        *,
        sections: List[PlanSectionSpec],
        count: int,
        language: str,
        excluded_section_ids: set[str] | None = None,
        slot_offset: int = 0,
    ) -> List[VisualSlotSpec]:
        if count <= 0 or not sections:
            return []
        excluded = set(excluded_section_ids or set())
        candidates = [sec for sec in sections if str(sec.section_id or "") not in excluded] or list(sections)
        slots: List[VisualSlotSpec] = []
        for idx in range(1, count + 1):
            section = candidates[(idx - 1) % len(candidates)]
            title = str(section.title or "正文").strip()
            excerpt = str(section.purpose or "").strip()[:260]
            if language == "zh":
                description = f"围绕最终正文《{title}》制作解释性信息图，准确呈现以下内容及其关系：{excerpt}"
            else:
                description = f"Create an explanatory visual grounded in the final section '{title}', accurately showing: {excerpt}"
            slots.append(
                VisualSlotSpec(
                    slot_id=f"final_v{slot_offset + idx}",
                    role="section_infographic",
                    anchor_section_id=str(section.section_id or ""),
                    description=description[:500],
                )
            )
        return slots
