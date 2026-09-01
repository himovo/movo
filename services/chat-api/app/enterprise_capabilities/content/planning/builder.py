from __future__ import annotations
from app.infrastructure.observability.config import log_print

import json
from typing import Any, Dict, List, Tuple

from app.llm.types import Message, Role
from app.llm.decision_turn import DecisionTurnSpec, invoke_json_decision, invoke_structured_decision

from app.llm.factory import get_llm_client
from app.enterprise_capabilities.content.planning.contracts import ContentPlanSpec, PlanSectionSpec, SectionFactSpec, VisualSlotSpec
from app.enterprise_capabilities.content.structure_roles import normalize_section_role
from app.enterprise_capabilities.content.merge_ops import deep_overlay_non_empty


class ContentPlanBuilder:
    def __init__(self) -> None:
        self._llm = None

    async def build(
        self,
        *,
        messages: List[Dict[str, Any]],
        content_task_spec: Dict[str, Any],
        content_schema: Dict[str, Any],
        output_spec: Dict[str, Any],
    ) -> ContentPlanSpec:
        semantic = None
        if not self._should_project_from_upstream(content_task_spec=content_task_spec, content_schema=content_schema):
            semantic = await self._semantic_build(
                messages=messages,
                content_task_spec=content_task_spec,
                content_schema=content_schema,
                output_spec=output_spec,
            )
        projected = self._project_build(
            content_task_spec=content_task_spec,
            content_schema=content_schema,
            output_spec=output_spec,
        )
        merged = self._merge_plan(projected, semantic) if semantic is not None else projected
        merged = self._enrich_plan_with_section_contracts(
            plan=merged,
            messages=messages,
            content_task_spec=content_task_spec,
            content_schema=content_schema,
            output_spec=output_spec,
        )
        self._log_plan(merged)
        return merged

    def _should_project_from_upstream(self, *, content_task_spec: Dict[str, Any], content_schema: Dict[str, Any]) -> bool:
        source = str(content_task_spec.get("source") or content_task_spec.get("assembly_source") or "").strip().lower()
        required_blocks = list(content_schema.get("required_blocks") or [])
        blocks = list(content_schema.get("blocks") or [])
        if source in {
            "user_provided_multimodal_summary",
            "multimodal_ui_analysis",
            "user_multimodal_payload",
        } and required_blocks and blocks:
            try:
                log_print(
                    "[content_plan] skip semantic planner for upstream multimodal contract "
                    f"| source={source} blocks={len(blocks)}",
                    flush=True,
                )
            except Exception:
                pass
            return True
        if str(content_task_spec.get("execution_kind") or "").strip() != "content":
            return False
        goal = content_task_spec.get("goal") if isinstance(content_task_spec.get("goal"), dict) else {}
        quality = content_task_spec.get("quality_targets") if isinstance(content_task_spec.get("quality_targets"), dict) else {}
        visual = content_task_spec.get("visual_plan") if isinstance(content_task_spec.get("visual_plan"), dict) else {}
        visual_assets = [item for item in list(visual.get("assets") or []) if isinstance(item, dict)]
        if bool(visual.get("required")) and (
            int(visual.get("min_assets") or 0) > 1
            or len(visual_assets) > 1
            or any(str(item.get("anchor") or "").strip().lower() == "auto" for item in visual_assets)
        ):
            return False
        return bool(goal) and bool(quality) and bool(required_blocks) and bool(blocks)

    async def _semantic_build(
        self,
        *,
        messages: List[Dict[str, Any]],
        content_task_spec: Dict[str, Any],
        content_schema: Dict[str, Any],
        output_spec: Dict[str, Any],
    ) -> ContentPlanSpec | None:
        task_meta = dict(content_task_spec.get("metadata") or {}) if isinstance(content_task_spec.get("metadata"), dict) else {}
        assembly_profile = dict(task_meta.get("assembly_profile") or {}) if isinstance(task_meta.get("assembly_profile"), dict) else {}
        medium = dict(content_task_spec.get("medium") or {}) if isinstance(content_task_spec.get("medium"), dict) else {}
        payload = {
            "messages": list(messages or [])[-8:],
            "content_task_spec": content_task_spec,
            "content_schema": content_schema,
            "profile_preset": dict(output_spec.get("profile_preset") or {}),
            "assembly_profile": assembly_profile,
            "medium": medium,
            "planning_evidence": dict(output_spec.get("planning_evidence") or {}) if isinstance(output_spec.get("planning_evidence"), dict) else {},
        }
        system = (
            "You are a planning agent responsible for building an executable ContentPlan for an AI writing runtime.\n"
            "The runtime will later generate both text and images based on your plan.\n"
            "Return ONLY strict structured output with fields:\n"
            "- plan_id\n"
            "- thesis\n"
            "- central_answer\n"
            "- execution_mode\n"
            "- sections(section_id, title, role, purpose, key_points, evidence_focus, visual_hint, target_words)\n"
            "- visual_slots(slot_id, role, anchor_section_id, description)\n"
            "- handoff_contract\n"
            "Do NOT write the final article.\n"
            "Schema rules:\n"
            "0) Return schema-valid JSON-compatible values only. Do not use prose strings for array or object fields.\n"
            "0.1) key_points and evidence_focus MUST be arrays of strings, even when there is only one item.\n"
            "0.2) allowed_claim_types, disallowed_claim_types, and open_questions MUST be arrays of strings.\n"
            "0.3) handoff_contract MUST be an object/dictionary, not a plain string. Put instructions under named keys.\n"
            "0.4) metadata, if present, MUST be an object/dictionary.\n"
            "Section rules:\n"
            "1) Reuse content_schema blocks as the primary structural source.\n"
            "2) Every section must have a concrete purpose.\n"
            "3) section_id must be stable and unique, such as s1, s2, s3.\n"
            "4) title must be a clear descriptive section title.\n"
            "5) key_points must be a JSON array listing the core ideas that must be covered.\n"
            "6) evidence_focus must be a JSON array describing the kinds of evidence or reasoning needed, such as examples, statistics, explanation, or comparison.\n"
            "7) visual_hint is only a short cue for the section; do NOT place full image prompts inside sections.\n"
            "8) target_words should be an approximate section word budget.\n"
            "Visual planning rules:\n"
            "9) All visual instructions must appear in visual_slots, not in reader-facing body sections.\n"
            "10) Each visual_slot must contain: slot_id, role, anchor_section_id, description.\n"
            "11) role should be a concise visual role string such as cover_illustration, architecture_diagram, mechanism_illustration, comparison_chart, infographic, process_diagram, application_scenarios_map, or timeline_chart.\n"
            "12) anchor_section_id must point to the section where the image belongs.\n"
            "13) description must be a clear image-generation brief including the subject, visual style, and context or environment.\n"
            "14) Avoid vague descriptions such as 'nice image' or 'relevant picture'.\n"
            "15) Add visual_slots when the section explains processes, systems, structures, comparisons, places, mechanisms, or applications.\n"
            "16) Do NOT add visuals when the section is purely narrative or abstract unless the overall deliverable explicitly requires richer illustration.\n"
            "17) Typical density is 0-2 visuals per section.\n"
            "18) If the deliverable is a publishable article or document with visuals, you may plan one default cover visual as the first visual_slot.\n"
            "19) If you add a default cover visual, use role='cover_illustration', anchor it to the opening or first substantive section, and make the description suitable for a polished title-cover image.\n"
            "Execution mode rules:\n"
            "20) execution_mode must be one of: sectional_compose or compact_block_compose.\n"
            "21) Use sectional_compose only for true long-form structured documents.\n"
            "22) Use compact_block_compose for shorter or mobile/social style content.\n"
            "23) If assembly_profile.length_band=short and assembly_profile.scannability=high, the plan MUST use execution_mode='compact_block_compose'.\n"
            "24) For compact_block_compose, sections are macro content blocks only, not article chapters.\n"
            "25) For compact_block_compose, do NOT create a table of contents, numbered hierarchy, outline-style section nesting, appendix-style blocks, or separate visual-planning sections.\n"
            "26) For compact_block_compose, prefer 3-5 reader-facing blocks with short mobile-friendly flow.\n"
            "27) Use execution_mode='sectional_compose' only for true long-form structured documents; never use it for short social/mobile content.\n"
            "28) If medium.channel indicates social/mobile reading, prefer compact_block_compose unless the task explicitly asks for a long report.\n"
            "29) Respect content_task_spec.writing_mode. If it is evidence_bound, section purposes and key_points must stay within supported facts; missing information should be expressed as confirmation gaps instead of invented capabilities.\n"
            "29.1) If planning_evidence is present, section purposes, key_points, evidence_focus, and visual_slots must follow that evidence for subject disambiguation and domain context. Do not introduce unsupported industries, use cases, or acronym expansions.\n"
            "Handoff contract rules:\n"
            "30) handoff_contract must be a JSON object describing how runtime should execute the plan, including text generation order, visual generation using visual_slots, insertion expectations, and output formatting expectations.\n"
            "Output rules:\n"
            "31) Return ONLY the structured ContentPlan.\n"
            "32) Do NOT include explanations.\n"
            "33) Do NOT generate the final article.\n"
            "34) Do NOT mix visual prompts inside sections.\n"
        )
        llm = self._llm or get_llm_client(streaming=False, stage="planning")
        last_error = ""
        for attempt in range(2):
            parsed, last_error = await self._try_structured_plan_build(
                llm=llm,
                system=system,
                payload=payload,
                previous_error=last_error,
            )
            if parsed is not None:
                return parsed
        try:
            raw_data = await invoke_json_decision(
                llm,
                [
                    Message(role=Role.SYSTEM, content=system
                        + "\nValidation failed in structured mode. Return JSON only. Keep every field schema-valid."
                    ),
                    Message(role=Role.USER, content=json.dumps(
                            {
                                "payload": payload,
                                "validation_error": last_error[:1200],
                            },
                            ensure_ascii=False,
                            default=str,
                        )
                    ),
                ],
                parser=lambda value: json.loads(self._extract_text(value)),
                spec=DecisionTurnSpec(
                    locale=str(output_spec.get("language") or output_spec.get("locale") or ""),
                    turn_id="content.plan.fallback",
                ),
            )
            normalized = self._normalize_content_plan_payload(raw_data)
            return ContentPlanSpec.model_validate(normalized)
        except Exception as exc:
            try:
                log_print(f"[content_plan] semantic build failed, using contract projection | error={type(exc).__name__}", flush=True)
            except Exception:
                pass
        return None

    async def _try_structured_plan_build(
        self,
        *,
        llm: Any,
        system: str,
        payload: Dict[str, Any],
        previous_error: str,
    ) -> Tuple[ContentPlanSpec | None, str]:
        prompt = system
        if previous_error:
            prompt += (
                "\nPrevious validation failed. Fix the structure instead of changing the plan intent.\n"
                f"Validation error summary: {previous_error[:1200]}"
            )
        try:
            parsed = await invoke_structured_decision(
                llm,
                ContentPlanSpec,
                [
                    Message(role=Role.SYSTEM, content=prompt),
                    Message(role=Role.USER, content=json.dumps(payload, ensure_ascii=False, default=str)),
                ],
                spec=DecisionTurnSpec(locale="", turn_id="content.plan"),
            )
            if isinstance(parsed, ContentPlanSpec):
                return parsed, ""
            return None, "structured_output_not_content_plan"
        except Exception as exc:
            return None, f"{type(exc).__name__}: {exc}"

    def _project_build(
        self,
        *,
        content_task_spec: Dict[str, Any],
        content_schema: Dict[str, Any],
        output_spec: Dict[str, Any],
    ) -> ContentPlanSpec:
        goal = dict(content_task_spec.get("goal") or {})
        quality = dict(content_task_spec.get("quality_targets") or {})
        visual = dict(content_task_spec.get("visual_plan") or {})
        artifact = dict(content_task_spec.get("artifact_contract") or {})
        blocks = list(content_schema.get("blocks") or [])
        min_words = int(((output_spec.get("profile_preset") or {}).get("quality_gates") or {}).get("min_words") or 0)
        max_words = int(((output_spec.get("profile_preset") or {}).get("quality_gates") or {}).get("max_words") or 0)
        total_target = max_words or min_words or 2400
        section_count = max(1, len(blocks))
        per_section = max(180, int(total_target / section_count))
        sections: List[PlanSectionSpec] = []
        for idx, block in enumerate(blocks, start=1):
            if not isinstance(block, dict):
                continue
            sections.append(
                PlanSectionSpec(
                    section_id=f"s{idx}",
                    title=str(block.get("title") or f"Section {idx}"),
                    role=normalize_section_role(str(block.get("role") or "").strip()),
                    purpose=str(block.get("purpose") or block.get("objective") or ""),
                    key_points=[str(x) for x in list(block.get("key_points") or []) if str(x).strip()][:6],
                    evidence_focus=[str(x) for x in list(block.get("evidence_focus") or []) if str(x).strip()][:6],
                    visual_hint=str(block.get("visual_hint") or "none").strip().lower(),
                    target_words=per_section,
                )
            )
        if not sections:
            sections.append(
                PlanSectionSpec(
                    section_id="s1",
                    title="Core Delivery",
                    role="core_body",
                    purpose="Deliver the requested output",
                    target_words=per_section,
                )
            )
        visual_slots = self._build_visual_slots(sections=sections, visual=visual)
        return ContentPlanSpec(
            plan_id=f"plan_{str(content_schema.get('schema_name') or 'default')}",
            thesis=str(goal.get("outcome") or goal.get("primary_action") or "").strip(),
            central_answer=str(goal.get("goal_type") or goal.get("outcome") or "").strip(),
            # Advisory only: writer execution mode is resolved later from compose policy
            # and content constraints, not inherited from schema shape.
            execution_mode="",
            sections=sections,
            visual_slots=visual_slots,
            handoff_contract={
                "expected_outputs": list(artifact.get("expected_outputs") or []),
                "publish_ready": bool(quality.get("publish_ready")),
            },
            metadata={"source": "contract_projection_builder"},
        )

    def _fallback_build(
        self,
        *,
        content_task_spec: Dict[str, Any],
        content_schema: Dict[str, Any],
        output_spec: Dict[str, Any],
    ) -> ContentPlanSpec:
        return self._project_build(
            content_task_spec=content_task_spec,
            content_schema=content_schema,
            output_spec=output_spec,
        )

    def _build_visual_slots(self, *, sections: List[PlanSectionSpec], visual: Dict[str, Any]) -> List[VisualSlotSpec]:
        slots: List[VisualSlotSpec] = []
        assets = [item for item in list(visual.get("assets") or []) if isinstance(item, dict)]
        min_assets = max(0, int(visual.get("min_assets") or 0))
        if assets:
            section_counts: Dict[str, int] = {}
            preferred_sections = list(sections[1:]) or list(sections)

            def _pick_balanced_section() -> str:
                ranked = sorted(
                    preferred_sections,
                    key=lambda sec: (int(section_counts.get(str(sec.section_id or ""), 0)), list(sections).index(sec)),
                )
                chosen = ranked[0] if ranked else (sections[0] if sections else None)
                return str((chosen.section_id if chosen else "") or "")

            for idx, asset in enumerate(assets, start=1):
                anchor = str(asset.get("anchor") or "").strip()
                anchor_id = ""
                if anchor:
                    for sec in sections:
                        if anchor in sec.title:
                            anchor_id = sec.section_id
                            break
                role = str(asset.get("role") or "").strip().lower()
                description = str(asset.get("description") or "").strip().lower()
                if not anchor_id and sections:
                    if idx == 1:
                        anchor_id = str((sections[0].section_id if sections else "") or "")
                    else:
                        anchor_id = _pick_balanced_section()
                if not anchor_id and sections:
                    anchor_id = _pick_balanced_section()
                section_counts[anchor_id] = int(section_counts.get(anchor_id, 0)) + 1
                slots.append(
                    VisualSlotSpec(
                        slot_id=f"v{idx}",
                        role=str(asset.get("role") or "visual"),
                        anchor_section_id=anchor_id,
                        description=str(asset.get("description") or asset.get("role") or "")[:200],
                    )
                )
            slots = self._top_up_visual_slots(
                slots=slots,
                sections=sections,
                min_assets=min_assets,
                base_description=str((assets[0] or {}).get("description") or "").strip(),
            )
            return slots[:8]
        for sec in sections:
            if sec.visual_hint and sec.visual_hint != "none":
                slots.append(
                    VisualSlotSpec(
                        slot_id=f"v_{sec.section_id}",
                        role=sec.visual_hint,
                        anchor_section_id=sec.section_id,
                        description=f"visual for {sec.title}",
                    )
                )
        slots = self._top_up_visual_slots(slots=slots, sections=sections, min_assets=min_assets, base_description="")
        return slots[:8]

    @staticmethod
    def _top_up_visual_slots(
        *,
        slots: List[VisualSlotSpec],
        sections: List[PlanSectionSpec],
        min_assets: int,
        base_description: str,
    ) -> List[VisualSlotSpec]:
        if min_assets <= len(slots) or not sections:
            return list(slots)
        out = list(slots)
        section_cycle = list(sections) or []
        default_roles = [
            "cover_illustration",
            "concept_diagram",
            "process_diagram",
            "application_scenarios_map",
            "summary_infographic",
        ]
        idx = len(out)
        while len(out) < min_assets and section_cycle:
            idx += 1
            section = section_cycle[(len(out)) % len(section_cycle)]
            role = default_roles[(len(out)) % len(default_roles)]
            description = base_description or f"visual for {str(section.title or '').strip()}"
            out.append(
                VisualSlotSpec(
                    slot_id=f"v{idx}",
                    role=role,
                    anchor_section_id=str(section.section_id or ""),
                    description=description[:200],
                )
            )
        return out

    def _merge_plan(self, projected: ContentPlanSpec, semantic: ContentPlanSpec) -> ContentPlanSpec:
        base = projected.model_dump()
        incoming = semantic.model_dump()
        merged = deep_overlay_non_empty(base, incoming)
        meta = dict(merged.get("metadata") or {})
        meta["source"] = "semantic_plus_projection"
        merged["metadata"] = meta
        return ContentPlanSpec.model_validate(merged)

    def _enrich_plan_with_section_contracts(
        self,
        *,
        plan: ContentPlanSpec,
        messages: List[Dict[str, Any]],
        content_task_spec: Dict[str, Any],
        content_schema: Dict[str, Any],
        output_spec: Dict[str, Any],
    ) -> ContentPlanSpec:
        inventory = self._build_fact_inventory(
            messages=messages,
            content_task_spec=content_task_spec,
            output_spec=output_spec,
        )
        schema_blocks = {
            str(item.get("title") or "").strip(): dict(item)
            for item in list(content_schema.get("blocks") or [])
            if isinstance(item, dict) and str(item.get("title") or "").strip()
        }
        enriched_sections: List[PlanSectionSpec] = []
        for idx, section in enumerate(list(plan.sections or []), start=1):
            sec = section.model_dump() if isinstance(section, PlanSectionSpec) else dict(section or {})
            contract = self._build_section_contract(
                section=dict(sec),
                schema_block=schema_blocks.get(str(sec.get("title") or "").strip()) or {},
                title=str(sec.get("title") or ""),
                role=normalize_section_role(str(sec.get("role") or "")),
                index=idx,
                total=len(list(plan.sections or [])),
                inventory=inventory,
                content_task_spec=content_task_spec,
                content_schema=content_schema,
            )
            if contract.get("purpose"):
                sec["purpose"] = str(contract.get("purpose") or "").strip()
            contract_role = normalize_section_role(str(contract.get("role") or ""))
            if contract_role:
                sec["role"] = contract_role
            for key in ("key_points", "evidence_focus", "allowed_claim_types", "disallowed_claim_types", "open_questions"):
                values = [str(x).strip() for x in list(contract.get(key) or []) if str(x).strip()]
                if values:
                    sec[key] = values
            fact_values = self._normalize_fact_specs(contract.get("must_cover_facts"))
            if fact_values:
                sec["must_cover_facts"] = fact_values
            enriched_sections.append(PlanSectionSpec.model_validate(sec))

        payload = plan.model_dump()
        payload["sections"] = [item.model_dump() for item in enriched_sections]
        metadata = dict(payload.get("metadata") or {})
        metadata["section_contracts"] = "enriched_from_fact_inventory"
        payload["metadata"] = metadata
        return ContentPlanSpec.model_validate(payload)

    def _normalize_content_plan_payload(self, data: Any) -> Dict[str, Any]:
        payload = dict(data or {}) if isinstance(data, dict) else {}
        payload["sections"] = self._normalize_sections(payload.get("sections"))
        payload["visual_slots"] = self._normalize_visual_slots(payload.get("visual_slots"))
        payload["handoff_contract"] = dict(payload.get("handoff_contract") or {}) if isinstance(payload.get("handoff_contract"), dict) else {}
        payload["metadata"] = dict(payload.get("metadata") or {}) if isinstance(payload.get("metadata"), dict) else {}
        return payload

    def _normalize_sections(self, value: Any) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        raw_items = value if isinstance(value, list) else [value] if isinstance(value, dict) else []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            record = dict(item)
            record["role"] = normalize_section_role(str(record.get("role") or "").strip())
            record["key_points"] = self._ensure_list_of_str(record.get("key_points"))
            record["evidence_focus"] = self._ensure_list_of_str(record.get("evidence_focus"))
            record["must_cover_facts"] = self._normalize_fact_specs(record.get("must_cover_facts"))
            record["allowed_claim_types"] = self._ensure_list_of_str(record.get("allowed_claim_types"))
            record["disallowed_claim_types"] = self._ensure_list_of_str(record.get("disallowed_claim_types"))
            record["open_questions"] = self._ensure_list_of_str(record.get("open_questions"))
            try:
                record["target_words"] = int(record.get("target_words") or 0)
            except Exception:
                record["target_words"] = 0
            items.append(record)
        return items

    @staticmethod
    def _last_user_text(messages: List[Dict[str, Any]]) -> str:
        for msg in reversed(list(messages or [])):
            if not isinstance(msg, dict):
                continue
            if str(msg.get("role") or "").strip().lower() != "user":
                continue
            return str(msg.get("content") or "").strip()
        return ""

    def _build_fact_inventory(
        self,
        *,
        messages: List[Dict[str, Any]],
        content_task_spec: Dict[str, Any],
        output_spec: Dict[str, Any],
    ) -> Dict[str, List[Dict[str, Any]]]:
        multimodal = output_spec.get("multimodal") if isinstance(output_spec.get("multimodal"), dict) else {}
        image_facts = multimodal.get("image_facts") if isinstance(multimodal.get("image_facts"), dict) else {}
        facts: Dict[str, List[Dict[str, Any]]] = {"all_facts": [], "open_questions": []}
        fact_index = 0

        def _limit_text(value: str, limit: int) -> str:
            token = str(value or "").strip()
            if len(token) <= limit:
                return token
            return token[:limit].rstrip() + "...[truncated]"

        def _push(bucket: str, *, summary: str, fact_type: str, source_kind: str, source_ref: str = "", raw_evidence: str = "") -> None:
            nonlocal fact_index
            token = _limit_text(str(summary or ""), 500)
            if not token:
                return
            if token.lower() in {"not identified from image", "none explicitly visible for interaction (navigation tabs only)"}:
                return
            seq = facts.setdefault(bucket, [])
            if any(str(item.get("summary") or "").strip() == token for item in seq if isinstance(item, dict)):
                return
            fact_index += 1
            seq.append(
                SectionFactSpec(
                    fact_id=f"fact_{fact_index}",
                    fact_type=str(fact_type or "").strip(),
                    summary=token,
                    source_kind=str(source_kind or "").strip(),
                    source_ref=str(source_ref or "").strip(),
                    raw_evidence=_limit_text(str(raw_evidence or token), 800),
                ).model_dump()
            )

        subject = str((output_spec.get("subject_resolution") or {}).get("canonical_subject") or "").strip() if isinstance(output_spec.get("subject_resolution"), dict) else ""
        if subject:
            _push("all_facts", summary=subject, fact_type="subject", source_kind="subject_resolution", source_ref="canonical_subject")

        for item in list(image_facts.get("cross_image_facts") or []):
            text = str(item or "").strip()
            if not text:
                continue
            _push(
                "all_facts",
                summary=text,
                fact_type="cross_image_fact",
                source_kind="cross_image_fact",
                raw_evidence=text,
            )

        for item in list(image_facts.get("ui_terms") or []):
            text = str(item or "").strip()
            if not text:
                continue
            _push("all_facts", summary=text, fact_type="ui_term", source_kind="ui_term", raw_evidence=text)

        publish_narrative = (
            content_task_spec.get("publish_narrative")
            if isinstance(content_task_spec.get("publish_narrative"), dict)
            else {}
        )
        for key in ("reader_problem", "narrative_goal", "opening_intent", "closing_intent"):
            token = str(publish_narrative.get(key) or "").strip()
            if token:
                _push(
                    "all_facts",
                    summary=token,
                    fact_type="narrative_contract",
                    source_kind="publish_narrative",
                    source_ref=key,
                    raw_evidence=token,
                )

        schema = content_task_spec.get("schema") if isinstance(content_task_spec.get("schema"), dict) else {}
        for spec in list(schema.get("section_specs") or []):
            if not isinstance(spec, dict):
                continue
            title = str(spec.get("title") or "").strip()
            for key in ("purpose", "visual_need"):
                token = str(spec.get(key) or "").strip()
                if token:
                    _push(
                        "all_facts",
                        summary=token,
                        fact_type="section_contract",
                        source_kind="section_spec",
                        source_ref=f"{title}:{key}" if title else key,
                        raw_evidence=token,
                    )
            for key in ("key_points", "evidence_focus", "must_cover_topics"):
                for item in list(spec.get(key) or []):
                    token = str(item or "").strip()
                    if token:
                        _push(
                            "all_facts",
                            summary=token,
                            fact_type="section_contract",
                            source_kind="section_spec",
                            source_ref=f"{title}:{key}" if title else key,
                            raw_evidence=token,
                        )

        for step in list(content_task_spec.get("subtasks") or []):
            if not isinstance(step, dict):
                continue
            title = str(step.get("title") or "").strip()
            objective = str(step.get("objective") or "").strip()
            if title:
                _push(
                    "all_facts",
                    summary=title,
                    fact_type="subtask",
                    source_kind="subtask",
                    source_ref=str(step.get("task_id") or "").strip(),
                    raw_evidence=title,
                )
            if objective:
                _push(
                    "all_facts",
                    summary=objective,
                    fact_type="subtask",
                    source_kind="subtask",
                    source_ref=str(step.get("task_id") or "").strip(),
                    raw_evidence=objective,
                )

        for image_idx, image in enumerate(list(image_facts.get("images") or []), start=1):
            if not isinstance(image, dict):
                continue
            area = str(image.get("page_area") or "").strip()
            flow = str(image.get("flow_relationship") or "").strip()
            controls = [str(x).strip() for x in list(image.get("controls") or []) if str(x).strip()]
            statuses = [str(x).strip() for x in list(image.get("status_tags") or []) if str(x).strip()]
            source_ref = f"image_{image_idx}"
            if area:
                _push("all_facts", summary=area, fact_type="page_area", source_kind="image_fact", source_ref=source_ref, raw_evidence=area)
            if flow and flow.lower() != "not identified from image":
                _push("all_facts", summary=flow, fact_type="flow_relationship", source_kind="image_fact", source_ref=source_ref, raw_evidence=flow)
            for token in controls + statuses:
                _push("all_facts", summary=token, fact_type="ui_control", source_kind="image_fact", source_ref=source_ref, raw_evidence=token)

        if not list(facts.get("all_facts") or []):
            fallback_goal = (
                str((content_task_spec.get("goal") or {}).get("outcome") or "").strip()
                if isinstance(content_task_spec.get("goal"), dict)
                else ""
            )
            fallback_text = fallback_goal or self._last_user_text(messages)
            fallback_text = str(fallback_text or "").strip()
            if fallback_text:
                _push(
                    "all_facts",
                    summary=fallback_text,
                    fact_type="task_goal",
                    source_kind="task_goal",
                    raw_evidence=fallback_text,
                )

        for item in list(image_facts.get("uncertain") or []):
            token = str(item or "").strip()
            if token:
                _push("open_questions", summary=token, fact_type="open_question", source_kind="image_fact", raw_evidence=token)

        return facts

    def _build_section_contract(
        self,
        *,
        section: Dict[str, Any],
        schema_block: Dict[str, Any],
        title: str,
        role: str,
        index: int,
        total: int,
        inventory: Dict[str, List[Dict[str, Any]]],
        content_task_spec: Dict[str, Any],
        content_schema: Dict[str, Any],
    ) -> Dict[str, Any]:
        role = normalize_section_role(str(role or "").strip()) or "core_body"
        role_defaults = self._role_contract_defaults(role=role)
        contracts: Dict[str, Any] = {
            "role": role,
            "purpose": str(schema_block.get("purpose") or section.get("purpose") or role_defaults.get("purpose") or "").strip(),
            "key_points": [str(x).strip() for x in list(schema_block.get("key_points") or section.get("key_points") or role_defaults.get("key_points") or []) if str(x).strip()][:8],
            "evidence_focus": [str(x).strip() for x in list(schema_block.get("evidence_focus") or section.get("evidence_focus") or role_defaults.get("evidence_focus") or []) if str(x).strip()][:8],
            "allowed_claim_types": [str(x).strip() for x in list(schema_block.get("allowed_claim_types") or section.get("allowed_claim_types") or role_defaults.get("allowed_claim_types") or []) if str(x).strip()][:8],
            "disallowed_claim_types": [str(x).strip() for x in list(schema_block.get("disallowed_claim_types") or section.get("disallowed_claim_types") or role_defaults.get("disallowed_claim_types") or []) if str(x).strip()][:8],
            "open_questions": [str(x).strip() for x in list(schema_block.get("open_questions") or section.get("open_questions") or []) if str(x).strip()][:8],
            "must_cover_facts": [],
        }
        query_parts: List[str] = [
            str(title or "").strip(),
            str(contracts.get("purpose") or "").strip(),
        ]
        query_parts.extend(list(contracts.get("key_points") or []))
        query_parts.extend(list(contracts.get("evidence_focus") or []))
        query_parts.extend([str(x).strip() for x in list(schema_block.get("must_cover_topics") or []) if str(x).strip()])
        selected = self._select_relevant_facts(
            facts=list(inventory.get("all_facts") or []),
            query_text=" ".join([part for part in query_parts if part]),
            preferred_source_kinds=list(role_defaults.get("preferred_source_kinds") or []),
            fallback_source_kinds=list(role_defaults.get("fallback_source_kinds") or []),
            limit=8,
        )
        contracts["must_cover_facts"] = self._normalize_fact_specs(
            self._retag_facts_for_role(role=role, facts=selected)
        )
        if not contracts["open_questions"]:
            contracts["open_questions"] = [
                str(item.get("summary") or "").strip()
                for item in list(inventory.get("open_questions") or [])
                if isinstance(item, dict) and str(item.get("summary") or "").strip()
            ][:6]
        return contracts

    @staticmethod
    def _retag_facts_for_role(*, role: str, facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        role = normalize_section_role(role)
        target_fact_type = ""
        if role == "data_metrics":
            target_fact_type = "metric_fact"
        elif role == "governance_constraints":
            target_fact_type = "constraint_fact"
        elif role == "interaction_flow":
            target_fact_type = "flow_fact"
        if not target_fact_type:
            return [dict(item) for item in list(facts or []) if isinstance(item, dict)]
        out: List[Dict[str, Any]] = []
        for item in list(facts or []):
            if not isinstance(item, dict):
                continue
            payload = dict(item)
            payload["fact_type"] = target_fact_type
            out.append(payload)
        return out

    @staticmethod
    def _role_contract_defaults(*, role: str) -> Dict[str, Any]:
        role = normalize_section_role(role)
        if role in {"background", "opening_context", "objective", "scope"}:
            return {
                "purpose": "明确任务背景、目标与范围边界。",
                "key_points": ["问题背景", "目标边界", "已知能力"],
                "evidence_focus": ["背景事实", "范围边界", "已确认模块能力"],
                "allowed_claim_types": ["background", "scope", "goal", "existing_capability"],
                "disallowed_claim_types": ["workflow_rule", "implementation_detail", "future_recommendation"],
                "preferred_source_kinds": ["cross_image_fact", "user_request", "subject_resolution"],
                "fallback_source_kinds": ["cross_image_fact", "user_request", "subject_resolution"],
            }
        if role in {"architecture", "module_overview"}:
            return {
                "purpose": "说明模块边界、数据流与整体闭环关系。",
                "key_points": ["模块职责", "闭环路径", "数据流转"],
                "evidence_focus": ["模块关系", "流程到数据的映射", "能力边界"],
                "allowed_claim_types": ["module_responsibility", "flow_relationship", "data_path"],
                "disallowed_claim_types": ["ui_rule", "field_default", "implementation_detail"],
                "preferred_source_kinds": ["cross_image_fact", "user_request", "image_fact"],
                "fallback_source_kinds": ["cross_image_fact", "user_request"],
            }
        if role in {"core_function_detail", "core_body"}:
            return {
                "purpose": "说明页面构成、关键字段、交互要点与模块能力。",
                "key_points": ["核心模块", "关键字段", "关键交互"],
                "evidence_focus": ["页面构成", "字段与状态", "按钮与视图"],
                "allowed_claim_types": ["page_component", "field", "interaction", "view_structure"],
                "disallowed_claim_types": ["implicit_business_rule", "permission_rule", "validation_rule"],
                "preferred_source_kinds": ["image_fact", "cross_image_fact", "user_request", "ui_term"],
                "fallback_source_kinds": ["image_fact", "cross_image_fact", "user_request"],
            }
        if role == "interaction_flow":
            return {
                "purpose": "按步骤说明输入、处理、确认与状态流转。",
                "key_points": ["步骤顺序", "输入输出", "状态流转"],
                "evidence_focus": ["流程步骤", "确认动作", "任务回溯"],
                "allowed_claim_types": ["step_definition", "input_output", "status_transition", "observed_interaction"],
                "disallowed_claim_types": ["relationship_structure", "state_machine_rule", "frontend_validation_rule"],
                "preferred_source_kinds": ["cross_image_fact", "user_request"],
                "fallback_source_kinds": ["cross_image_fact", "user_request"],
            }
        if role == "data_metrics":
            return {
                "purpose": "定义指标口径、统计范围、来源字段与流程映射。",
                "key_points": ["指标定义", "统计范围", "来源字段"],
                "evidence_focus": ["指标名称", "字段来源", "流程映射"],
                "allowed_claim_types": ["metric_definition", "metric_scope", "metric_source"],
                "disallowed_claim_types": ["recommendation", "optimization_strategy", "future_prediction"],
                "preferred_source_kinds": ["cross_image_fact", "user_request", "ui_term"],
                "fallback_source_kinds": ["cross_image_fact", "user_request", "ui_term"],
            }
        if role == "governance_constraints":
            return {
                "purpose": "说明参数边界、状态语义、适用条件与待确认项。",
                "key_points": ["参数边界", "状态语义", "口径边界"],
                "evidence_focus": ["约束条件", "状态说明", "统计边界"],
                "allowed_claim_types": ["constraint_definition", "parameter_boundary", "status_semantics", "boundary_note"],
                "disallowed_claim_types": ["metric_definition", "recommendation", "implementation_detail"],
                "preferred_source_kinds": ["ui_term", "user_request", "cross_image_fact"],
                "fallback_source_kinds": ["ui_term", "user_request", "cross_image_fact"],
            }
        if role in {"closing", "risk_or_boundary"}:
            return {
                "purpose": "收束判断并明确风险、边界或后续动作。",
                "key_points": ["结论", "风险边界", "后续动作"],
                "evidence_focus": ["已确认结论", "边界说明", "待确认项"],
                "allowed_claim_types": ["summary", "boundary_note", "next_step"],
                "disallowed_claim_types": ["new_feature", "new_metric", "implementation_detail"],
                "preferred_source_kinds": ["cross_image_fact", "user_request", "subject_resolution"],
                "fallback_source_kinds": ["cross_image_fact", "user_request", "subject_resolution"],
            }
        return {
            "purpose": "围绕本节已确认事实组织内容。",
            "key_points": [],
            "evidence_focus": ["关键事实与支撑依据"],
            "allowed_claim_types": ["supported_fact"],
            "disallowed_claim_types": ["unsupported_rule"],
            "preferred_source_kinds": ["cross_image_fact", "user_request", "image_fact", "ui_term"],
            "fallback_source_kinds": ["cross_image_fact", "user_request"],
        }

    def _select_relevant_facts(
        self,
        *,
        facts: List[Dict[str, Any]],
        query_text: str,
        preferred_source_kinds: List[str],
        fallback_source_kinds: List[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        ranked: List[Tuple[int, int, Dict[str, Any]]] = []
        preferred = {str(item).strip() for item in list(preferred_source_kinds or []) if str(item).strip()}
        fallback = {str(item).strip() for item in list(fallback_source_kinds or []) if str(item).strip()}
        for idx, item in enumerate(list(facts or [])):
            if not isinstance(item, dict):
                continue
            summary = str(item.get("summary") or "").strip()
            if not summary:
                continue
            source_kind = str(item.get("source_kind") or "").strip()
            priority = self._fact_source_priority(
                source_kind=source_kind,
                preferred_source_kinds=preferred_source_kinds,
                fallback_source_kinds=fallback_source_kinds,
            )
            if priority <= 0:
                continue
            ranked.append((priority, -idx, item))
        ranked.sort(reverse=True)
        selected: List[Dict[str, Any]] = []
        seen = set()
        for _, _, item in ranked:
            summary = str(item.get("summary") or "").strip()
            if not summary or summary in seen:
                continue
            seen.add(summary)
            selected.append(item)
            if len(selected) >= limit:
                break
        if selected:
            return selected
        # Final fallback only when no role-aligned source kinds exist: keep the earliest globally confirmed facts.
        out: List[Dict[str, Any]] = []
        for item in list(facts or []):
            if not isinstance(item, dict):
                continue
            summary = str(item.get("summary") or "").strip()
            source_kind = str(item.get("source_kind") or "").strip()
            if not summary or summary in seen:
                continue
            if fallback and source_kind and source_kind not in fallback:
                continue
            seen.add(summary)
            out.append(item)
            if len(out) >= min(limit, 4):
                break
        return out

    @staticmethod
    def _fact_source_priority(
        *,
        source_kind: str,
        preferred_source_kinds: List[str],
        fallback_source_kinds: List[str],
    ) -> int:
        token = str(source_kind or "").strip()
        if not token:
            return 0
        preferred = [str(item).strip() for item in list(preferred_source_kinds or []) if str(item).strip()]
        fallback = [str(item).strip() for item in list(fallback_source_kinds or []) if str(item).strip()]
        if token in preferred:
            return len(preferred) - preferred.index(token) + len(fallback) + 1
        if token in fallback:
            return len(fallback) - fallback.index(token) + 1
        return 0

    def _normalize_visual_slots(self, value: Any) -> List[Dict[str, Any]]:
        raw_items = value if isinstance(value, list) else [value] if isinstance(value, dict) else []
        return [dict(item) for item in raw_items if isinstance(item, dict)]

    @staticmethod
    def _extract_text(value: Any) -> str:
        if isinstance(value, str):
            return value
        content = getattr(value, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(str(item.get("text") or "") for item in content if isinstance(item, dict))
        return str(content or "")

    @staticmethod
    def _ensure_list_of_str(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if value is None:
            return []
        token = str(value).strip()
        return [token] if token else []

    @staticmethod
    def _normalize_fact_specs(value: Any) -> List[Dict[str, Any]]:
        items = value if isinstance(value, list) else [value] if value else []
        out: List[Dict[str, Any]] = []
        seen = set()
        for idx, item in enumerate(items, start=1):
            if isinstance(item, dict):
                payload = dict(item)
            else:
                token = str(item or "").strip()
                if not token:
                    continue
                payload = {
                    "fact_id": f"fact_{idx}",
                    "fact_type": "fact",
                    "summary": token,
                    "source_kind": "legacy_text",
                    "source_ref": "",
                    "raw_evidence": token,
                }
            summary = str(payload.get("summary") or "").strip()
            if not summary or summary in seen:
                continue
            seen.add(summary)
            out.append(SectionFactSpec.model_validate(payload).model_dump())
        return out

    @staticmethod
    def _log_plan(plan: ContentPlanSpec) -> None:
        try:
            log_print(
                "[content_plan] plan built | id=%s mode=%s sections=%s visual_slots=%s source=%s"
                % (
                    str(plan.plan_id or ""),
                    str(plan.execution_mode or ""),
                    len(plan.sections),
                    len(plan.visual_slots),
                    str((plan.metadata or {}).get("source") or ""),
                ),
                flush=True,
            )
        except Exception:
            pass
