from __future__ import annotations
from app.infrastructure.observability.config import log_print

import json
import logging
import re
from typing import Any, AsyncIterator, Dict, List, Tuple

import yaml
from app.llm.types import Message, Role

from app.enterprise_capabilities.content.body_projection import (
    canonicalize_required_blocks,
    strip_visual_or_production_clauses,
    strip_visual_placeholder_directives,
)
from app.enterprise_capabilities.content.structure_roles import contains_cjk
from app.enterprise_capabilities.content.writer_engine.skill_contract import BaseSkill, SkillContext
from app.services.image_assets import build_embedded_document_image_assets
from app.services.image_markdown import inject_images_inline, merge_image_layout_hints, normalize_image_markdown
from app.services.image_planner import get_image_planner_service
from app.enterprise_capabilities.content.writer_engine.pipeline import WriterEnginePipeline
from app.enterprise_capabilities.content.argument_pack import ArgumentPackSelector
from app.enterprise_capabilities.content.planning import build_body_plan
from app.enterprise_capabilities.evidence.foundation.external_web_raw import strip_external_web_raw
from app.enterprise_capabilities.evidence.foundation import normalize_evidence_bundle
from app.enterprise_capabilities.evidence.foundation.writer_packet import WriterEvidencePacketBuilder, persist_writer_evidence_packet
from app.enterprise_capabilities.evidence.foundation.fair_selection import round_robin_take
from app.enterprise_capabilities.evidence.foundation.graph_artifact_projector import project_graph_artifact_result
from app.enterprise_capabilities.evidence.foundation.user_request_fact_extractor import enrich_evidence_with_user_request_facts
from app.enterprise_capabilities.content.execution_mode import ExecutionModeResolver
from app.enterprise_capabilities.content.compose_access import resolve_compose_policy
from app.enterprise_capabilities.content.style_contract_renderer import resolve_writer_style_prompt
from app.enterprise_capabilities.content.structure_roles import normalize_section_roles
from app.enterprise_capabilities.content.subject_resolution import CandidateAnalyzer, SubjectResolutionResolver


class ToolWriterEngineComposeSkill(BaseSkill):
    name = "tool_writer_engine_compose"
    description = "Unified bottom-layer writing engine driven by profile preset."

    def __init__(self) -> None:
        self._pipeline = WriterEnginePipeline()
        self._argument_selector = ArgumentPackSelector()
        self._mode_resolver = ExecutionModeResolver()
        self._subject_resolver = SubjectResolutionResolver()

    @staticmethod
    def _strip_outer_markdown_fence(text: str) -> str:
        raw = str(text or "").strip()
        if not raw:
            return raw
        m = re.match(r"^\s*```(?:md|markdown)?\s*\n([\s\S]*?)\n```\s*$", raw, flags=re.IGNORECASE)
        if not m:
            return raw
        inner = str(m.group(1) or "").strip()
        return inner

    @staticmethod
    def _truncate_text(value: Any, limit: int = 1800) -> str:
        raw = str(value or "")
        if len(raw) <= limit:
            return raw
        return raw[:limit] + "...<truncated>"

    @staticmethod
    def _normalize_writing_mode(value: Any) -> str:
        token = str(value or "").strip().lower()
        if token in {"creative", "hybrid", "evidence_bound"}:
            return token
        return "hybrid"

    @staticmethod
    def _target_words_from_quality(quality_gates: Dict[str, Any]) -> int:
        target = int(quality_gates.get("target_words") or 0)
        min_words = int(quality_gates.get("min_words") or 0)
        max_words = int(quality_gates.get("max_words") or 0)
        if target > 0:
            return target
        if min_words > 0 and max_words >= min_words:
            return (min_words + max_words) // 2
        return max_words or min_words or 0

    @staticmethod
    def _is_report_like_deliverable(output_spec: Dict[str, Any], strategy: Dict[str, Any]) -> bool:
        preset = output_spec.get("profile_preset") if isinstance(output_spec.get("profile_preset"), dict) else {}
        compose = preset.get("compose_policy") if isinstance(preset.get("compose_policy"), dict) else {}
        output_contract = preset.get("output_contract") if isinstance(preset.get("output_contract"), dict) else {}
        content_task_spec = output_spec.get("content_task_spec") if isinstance(output_spec.get("content_task_spec"), dict) else {}
        schema = content_task_spec.get("schema") if isinstance(content_task_spec.get("schema"), dict) else {}
        goal = content_task_spec.get("goal") if isinstance(content_task_spec.get("goal"), dict) else {}
        strategy_compose = strategy.get("compose_policy") if isinstance(strategy.get("compose_policy"), dict) else {}
        strategy_output = strategy.get("output_contract") if isinstance(strategy.get("output_contract"), dict) else {}
        tokens = {
            str(compose.get("content_form") or "").strip().lower(),
            str(output_contract.get("deliverable") or "").strip().lower(),
            str(strategy_compose.get("content_form") or "").strip().lower(),
            str(strategy_output.get("deliverable") or "").strip().lower(),
            str(schema.get("category") or "").strip().lower(),
            str(goal.get("primary_action") or "").strip().lower(),
            str(output_spec.get("_dynamic_deliverable_signature") or "").strip().lower(),
        }
        report_like = {
            "report",
            "document",
            "document_scale",
            "prd",
            "plan",
            "proposal",
            "solution",
            "方案",
            "whitepaper",
            "handbook",
            "analysis_report",
            "research_report",
            "product_requirements_document",
            "compose_report",
            "document_scale",
        }
        return bool(tokens.intersection(report_like))

    @staticmethod
    def _has_planned_generated_visuals(strategy: Dict[str, Any], output_spec: Dict[str, Any]) -> bool:
        content_task_spec = output_spec.get("content_task_spec") if isinstance(output_spec.get("content_task_spec"), dict) else {}
        visual_plan = content_task_spec.get("visual_plan") if isinstance(content_task_spec.get("visual_plan"), dict) else {}
        if int(visual_plan.get("min_assets") or 0) > 0:
            return True
        visual_policy = strategy.get("visual_policy") if isinstance(strategy.get("visual_policy"), dict) else {}
        if int(visual_policy.get("min_visuals_per_report") or 0) > 0:
            return True
        if int(visual_policy.get("min_infographics_per_report") or 0) > 0:
            return True
        return False

    @staticmethod
    def _body_document_shape(output_spec: Dict[str, Any], content_form: str = "") -> str:
        content_task_spec = output_spec.get("content_task_spec") if isinstance(output_spec.get("content_task_spec"), dict) else {}
        schema = content_task_spec.get("schema") if isinstance(content_task_spec.get("schema"), dict) else {}
        goal = content_task_spec.get("goal") if isinstance(content_task_spec.get("goal"), dict) else {}
        task_ir = output_spec.get("task_ir") if isinstance(output_spec.get("task_ir"), dict) else {}
        text = " ".join(
            [
                str(content_form or ""),
                str(output_spec.get("_dynamic_deliverable_signature") or ""),
                str(schema.get("name") or ""),
                str(schema.get("type") or ""),
                str(schema.get("category") or ""),
                str(goal.get("primary_action") or ""),
                str(goal.get("outcome") or ""),
                str(task_ir.get("deliverable_mode") or ""),
                str(output_spec.get("_timeline_user_text") or ""),
            ]
        ).strip().lower()
        if any(token in text for token in ("manual", "handbook", "instruction", "说明书", "手册", "largemodelusermanual")):
            return "manual"
        if any(token in text for token in ("guide", "tutorial", "指南", "教程")):
            return "guide"
        if any(token in text for token in ("faq", "常见问题")):
            return "faq"
        if any(token in text for token in ("sop", "standard operating procedure", "操作规程", "标准作业")):
            return "sop"
        if any(token in text for token in ("prd", "product_requirements_document")):
            return "prd"
        return str(content_form or "").strip().lower()

    @classmethod
    def _body_base_instruction(cls, output_spec: Dict[str, Any], content_form: str) -> str:
        shape = cls._body_document_shape(output_spec, content_form=content_form)
        if shape == "manual":
            return "写成一份可直接照着使用的说明书，重点是适用对象、基本概念、使用准备、操作步骤、注意事项和常见问题；不要写成背景分析报告"
        if shape == "guide":
            return "写成一份实用指南，重点是操作路径、示例、检查清单和注意事项；不要写成调研报告"
        if shape == "faq":
            return "写成一份问答式 FAQ，围绕用户真实问题逐条回答，避免报告式背景分析"
        if shape == "sop":
            return "写成一份标准操作规程，重点是适用范围、职责、步骤、检查点和异常处理"
        if shape == "prd":
            return "写成一份产品需求文档，重点是目标、用户场景、功能需求、非功能需求和验收标准"
        if shape in {"report", "document_scale"}:
            return "写成一份结构完整、面向协作和评审的正式报告"
        if shape == "plan":
            return "写成一份可执行、可落地的方案文档"
        if shape in {"document", "brief", "memo"}:
            return "写成一份面向最终读者的结构化文档，直接进入主题，避免报告式背景铺垫"
        return "写成一篇面向最终读者的可发布文章"

    @staticmethod
    def _merge_uploaded_assets(existing_assets: List[Dict[str, Any]], new_assets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        seen = set()
        for asset in [*list(existing_assets or []), *list(new_assets or [])]:
            if not isinstance(asset, dict):
                continue
            key = (
                str(asset.get("asset_id") or "").strip(),
                str(asset.get("object_path") or "").strip(),
                str(asset.get("path") or asset.get("signed_url") or "").strip(),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(dict(asset))
        return merged

    @classmethod
    def _collect_uploaded_assets_for_compose(cls, output_spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        multimodal = output_spec.get("multimodal") if isinstance(output_spec.get("multimodal"), dict) else {}
        assets = [dict(x) for x in list(multimodal.get("uploaded_assets") or []) if isinstance(x, dict)]

        parsed_documents: List[Dict[str, Any]] = []
        documents = output_spec.get("documents") if isinstance(output_spec.get("documents"), dict) else {}
        parsed_documents.extend(
            dict(x) for x in list(documents.get("parsed_documents") or []) if isinstance(x, dict)
        )
        for artifact_bucket_key in ("input_artifacts", "predecessor_artifacts"):
            artifact_bucket = output_spec.get(artifact_bucket_key)
            if not isinstance(artifact_bucket, dict):
                continue
            for artifact in artifact_bucket.values():
                if not isinstance(artifact, dict):
                    continue
                parsed_documents.extend(
                    dict(x) for x in list(artifact.get("parsed_documents") or []) if isinstance(x, dict)
                )
                nested_documents = artifact.get("documents") if isinstance(artifact.get("documents"), dict) else {}
                parsed_documents.extend(
                    dict(x) for x in list(nested_documents.get("parsed_documents") or []) if isinstance(x, dict)
                )

        embedded_assets: List[Dict[str, Any]] = []
        seen_docs = set()
        for doc in parsed_documents:
            doc_key = (
                str(doc.get("asset_id") or "").strip(),
                str(doc.get("filename") or "").strip(),
                len(list(doc.get("embedded_images") or [])),
            )
            if doc_key in seen_docs:
                continue
            seen_docs.add(doc_key)
            embedded_assets.extend(
                build_embedded_document_image_assets(
                    embedded_images=[dict(x) for x in list(doc.get("embedded_images") or []) if isinstance(x, dict)],
                    source_document_id=str(doc.get("asset_id") or doc.get("filename") or "").strip(),
                )
            )
        return cls._merge_uploaded_assets(assets, embedded_assets)

    @staticmethod
    def _build_strategy(output_spec: Dict[str, Any]) -> Dict[str, Any]:
        preset = output_spec.get("profile_preset") if isinstance(output_spec.get("profile_preset"), dict) else {}
        _is_dynamic_preset = str((preset or {}).get("source") or "").strip().lower() == "dynamic"
        prompt_contract = output_spec.get("prompt_contract") if isinstance(output_spec.get("prompt_contract"), dict) else {}
        production_contract = output_spec.get("production_contract") if isinstance(output_spec.get("production_contract"), dict) else {}
        content_plan = output_spec.get("content_plan") if isinstance(output_spec.get("content_plan"), dict) else {}
        argument_pack = output_spec.get("argument_pack") if isinstance(output_spec.get("argument_pack"), dict) else {}
        visual_semantics = output_spec.get("visual_semantics") if isinstance(output_spec.get("visual_semantics"), dict) else {}
        content_task_spec = output_spec.get("content_task_spec") if isinstance(output_spec.get("content_task_spec"), dict) else {}
        structure = preset.get("structure_contract") if isinstance(preset.get("structure_contract"), dict) else {}
        evidence = preset.get("evidence_policy") if isinstance(preset.get("evidence_policy"), dict) else {}
        visual = preset.get("visual_contract") if isinstance(preset.get("visual_contract"), dict) else {}
        gates = preset.get("quality_gates") if isinstance(preset.get("quality_gates"), dict) else {}
        compose = preset.get("compose_policy") if isinstance(preset.get("compose_policy"), dict) else {}
        # Carry top-level output_spec.compose_policy into strategy when preset is empty
        # OR when the top-level overrides carry signals the preset doesn't have
        # (evidence_strength_hint and pinned section/length constraints).
        # Preset values stay authoritative when both are present.
        top_compose = output_spec.get("compose_policy") if isinstance(output_spec.get("compose_policy"), dict) else {}
        if isinstance(top_compose, dict):
            merged_compose = dict(top_compose)
            for k, v in (compose or {}).items():
                if v not in (None, "", [], {}):
                    merged_compose[k] = v
            compose = merged_compose

        required_blocks = list(structure.get("required_blocks") or output_spec.get("required_blocks") or [])
        explicit_count = int(structure.get("section_count") or 0)
        # Prefer concrete block list cardinality to avoid stale section_count drift.
        section_count = len(required_blocks) if required_blocks else (explicit_count if explicit_count > 0 else 8)
        section_count = max(1, min(section_count, 18))
        body_plan = build_body_plan(structure=structure, content_plan=content_plan)
        visual_plan = dict(content_task_spec.get("visual_plan") or {})
        min_images = max(0, int(visual_plan.get("min_assets") or 0))
        max_images = max(min_images, int(visual_plan.get("max_assets") or 0))
        if max_images < min_images:
            max_images = min_images
        min_words = int(gates.get("min_words") or 0)
        max_words = int(gates.get("max_words") or 0)
        target_words = int(gates.get("target_words") or 0)
        if target_words <= 0:
            if min_words > 0 and max_words >= min_words:
                target_words = (min_words + max_words) // 2
            elif max_words > 0:
                target_words = max_words
            elif _is_dynamic_preset:
                # Dynamic preset with no word signal: conservative short-form
                # default rather than 2600 (which is article-shaped).
                target_words = 800
            else:
                target_words = 2600
        section_min = int(gates.get("section_min_words") or 220)
        section_max = int(gates.get("section_max_words") or 650)
        if section_max < section_min:
            section_max = section_min

        # For dynamic presets (unknown deliverable types — resume, email,
        # manual), default to "none" instead of "hierarchical": short
        # structured docs should not get 1./2./3. numbering by accident.
        _numbering_default = "none" if _is_dynamic_preset else "hierarchical"
        _numbering_style = str(structure.get("numbering_style") or _numbering_default).strip().lower()
        if _numbering_style not in {"hierarchical", "flat", "clause", "none"}:
            _numbering_style = _numbering_default
        strategy = {
            "section_count": section_count,
            "outline_depth": int(structure.get("outline_depth") or 2),
            "numbering_style": _numbering_style,
            "word_budget": {
                "total_target": target_words,
                "section_min": section_min,
                "section_max": section_max,
            },
            "visual_policy": {
                "min_visuals_per_report": min_images,
                "max_visuals_per_report": max_images,
                "min_infographics_per_report": min_images,
                "max_infographics_per_report": max_images,
                "include_infographics": bool(min_images > 0 or list(visual_plan.get("assets") or [])),
            },
            "compose_policy": dict(compose),
            "structure_contract": dict(structure),
            "evidence_policy": dict(evidence),
            "visual_contract": dict(visual),
            "quality_gates": dict(gates),
            "output_contract": dict(preset.get("output_contract") or {}),
            "forbidden_patterns": list(preset.get("forbidden_patterns") or []),
            "prompt_contract": dict(prompt_contract),
            "production_contract": dict(production_contract),
            "content_plan": dict(content_plan),
            "body_plan": dict(body_plan),
            "content_task_spec": dict(content_task_spec),
            "writing_mode": ToolWriterEngineComposeSkill._normalize_writing_mode(content_task_spec.get("writing_mode")),
            "argument_pack": dict(argument_pack),
            "visual_semantics": dict(visual_semantics),
        }
        # Doc-level eval feedback (set by task_satisfaction_eval on retry):
        # mirror onto strategy so the writer engine's generate methods can
        # read it via the same field regardless of which entry path runs.
        _doc_feedback = str(output_spec.get("__doc_level_eval_feedback") or "").strip()
        if _doc_feedback:
            strategy["doc_level_feedback"] = _doc_feedback
        try:
            log_print(
                "[tool_writer_engine_compose][strategy] dynamic=%s section_count=%s "
                "numbering=%s target_words=%s min/max=%s/%s min_imgs=%s "
                "content_form=%s blocks=%s"
                % (
                    _is_dynamic_preset,
                    section_count,
                    _numbering_style,
                    target_words,
                    min_words,
                    max_words,
                    min_images,
                    str(compose.get("content_form") or ""),
                    json.dumps(list(structure.get("required_blocks") or []), ensure_ascii=False),
                ),
                flush=True,
            )
        except Exception:
            pass
        return strategy

    def _decide_execution_mode(self, *, strategy: Dict[str, Any], output_spec: Dict[str, Any], user_query: str) -> Dict[str, Any]:
        decision = self._mode_resolver.resolve(
            compose_policy=strategy.get("compose_policy") if isinstance(strategy.get("compose_policy"), dict) else {},
            structure_contract=strategy.get("structure_contract") if isinstance(strategy.get("structure_contract"), dict) else {},
            quality_gates=strategy.get("quality_gates") if isinstance(strategy.get("quality_gates"), dict) else {},
            evidence_policy=strategy.get("evidence_policy") if isinstance(strategy.get("evidence_policy"), dict) else {},
            prompt_contract=strategy.get("prompt_contract") if isinstance(strategy.get("prompt_contract"), dict) else {},
            user_query=user_query,
        )
        return decision.model_dump()

    def _attach_section_arguments(self, strategy: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(strategy or {})
        body_plan = out.get("body_plan") if isinstance(out.get("body_plan"), dict) else {}
        argument_pack = out.get("argument_pack") if isinstance(out.get("argument_pack"), dict) else {}
        sections = [item for item in list(body_plan.get("sections") or []) if isinstance(item, dict)]
        if not sections or not argument_pack:
            return out
        enriched = []
        for sec in sections:
            item = dict(sec)
            item["argument_items"] = self._argument_selector.select_for_section(
                argument_pack=argument_pack,
                title=str(item.get("title") or ""),
                objective=str(item.get("purpose") or item.get("objective") or ""),
                evidence_focus=[str(x) for x in list(item.get("evidence_focus") or []) if str(x).strip()],
            )
            enriched.append(item)
        updated_plan = dict(body_plan)
        updated_plan["sections"] = enriched
        out["body_plan"] = updated_plan
        return out

    @staticmethod
    def _ensure_runtime_contract(strategy: Dict[str, Any], output_spec: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(strategy or {})
        compose = out.get("compose_policy") if isinstance(out.get("compose_policy"), dict) else {}
        structure = out.get("structure_contract") if isinstance(out.get("structure_contract"), dict) else {}
        evidence = out.get("evidence_policy") if isinstance(out.get("evidence_policy"), dict) else {}
        quality = out.get("quality_gates") if isinstance(out.get("quality_gates"), dict) else {}
        output = out.get("output_contract") if isinstance(out.get("output_contract"), dict) else {}
        gp = resolve_compose_policy(output_spec)
        effective_policy = output_spec.get("effective_policy") if isinstance(output_spec.get("effective_policy"), dict) else {}
        effective_compose = (
            effective_policy.get("compose_policy") if isinstance(effective_policy.get("compose_policy"), dict) else {}
        )
        effective_sections = [str(x).strip() for x in (effective_compose.get("required_sections") or []) if str(x).strip()]
        compose_sections = [str(x).strip() for x in (compose.get("required_sections") or []) if str(x).strip()]
        required_blocks = [str(x).strip() for x in (structure.get("required_blocks") or []) if str(x).strip()]
        output_blocks = [str(x).strip() for x in (output_spec.get("required_blocks") or []) if str(x).strip()]
        if not output_blocks:
            output_blocks = [str(x).strip() for x in (gp.get("required_sections") or []) if str(x).strip()]

        # Authoritative source ranking for required_blocks:
        #   - For dynamic-source presets, the SYNTH's structure_contract wins.
        #     Upstream `compose.required_sections` is often a single sentence
        #     describing the deliverable (e.g.
        #     ["撰写用于求职投递与面试评估的专业简历文档report"]) — meant as a
        #     deliverable descriptor, not as a section list. Letting it win
        #     collapses synth's 6-7 resume blocks into a single bogus section.
        #   - For non-dynamic (builtin presets / catalog), compose policy stays
        #     authoritative as before.
        _preset_for_order = output_spec.get("profile_preset") if isinstance(output_spec.get("profile_preset"), dict) else {}
        _is_dynamic_preset = str((_preset_for_order or {}).get("source") or "").strip().lower() == "dynamic"
        if _is_dynamic_preset and required_blocks:
            # Keep synth's structure_contract.required_blocks; ignore upstream noise.
            pass
        elif compose_sections:
            required_blocks = compose_sections
        elif effective_sections:
            required_blocks = effective_sections
        else:
            if len(output_blocks) > len(required_blocks):
                required_blocks = output_blocks
            if not required_blocks:
                required_blocks = output_blocks
        if not required_blocks:
            required_blocks = ["核心内容"]
        # Dynamic-source presets carry user-facing order from the synthesiser
        # (resume → header→summary→experience→…). canonicalize_required_blocks's
        # weight map is article-shaped and would shuffle those into alphabetical
        # order. Preserve order in dynamic mode.
        required_blocks = canonicalize_required_blocks(required_blocks, preserve_order=_is_dynamic_preset)
        structure["required_blocks"] = required_blocks
        section_roles = [str(x).strip() for x in list(structure.get("section_roles") or []) if str(x).strip()]
        if not section_roles:
            structure_blocks = [item for item in list(structure.get("blocks") or []) if isinstance(item, dict)]
            section_roles = normalize_section_roles([str(item.get("role") or "") for item in structure_blocks])
        if not section_roles:
            body_plan = out.get("body_plan") if isinstance(out.get("body_plan"), dict) else {}
            body_sections = [item for item in list(body_plan.get("sections") or []) if isinstance(item, dict)]
            section_roles = normalize_section_roles([str(item.get("role") or "") for item in body_sections])
        if not section_roles:
            content_plan = out.get("content_plan") if isinstance(out.get("content_plan"), dict) else {}
            content_sections = [item for item in list(content_plan.get("sections") or []) if isinstance(item, dict)]
            section_roles = normalize_section_roles([str(item.get("role") or "") for item in content_sections])
        if section_roles:
            structure["section_roles"] = section_roles[:8]
        structure.setdefault("section_count", max(1, len(required_blocks)))
        schema_planning_mode = str(structure.get("planning_mode") or "").strip()
        if schema_planning_mode and not str(structure.get("schema_planning_mode") or "").strip():
            structure["schema_planning_mode"] = schema_planning_mode
        structure.pop("planning_mode", None)

        compose["tone"] = str(compose.get("tone") or gp.get("tone") or "professional").strip()
        compose["content_form"] = str(compose.get("content_form") or gp.get("content_form") or "article").strip()
        writing_mode = ToolWriterEngineComposeSkill._normalize_writing_mode(
            out.get("writing_mode")
            or output_spec.get("writing_mode")
            or ((out.get("content_task_spec") or {}).get("writing_mode") if isinstance(out.get("content_task_spec"), dict) else "")
        )
        compose["writing_mode"] = writing_mode
        write_mode = str(compose.get("write_mode") or gp.get("write_mode") or "auto").strip().lower()
        if write_mode == "structured":
            write_mode = "sectional"
        if write_mode not in {"direct", "compact_block", "sectional", "document_scale", "auto"}:
            write_mode = "auto"
        compose["write_mode"] = write_mode
        normalized_content_form = str(compose.get("content_form") or "").strip().lower()
        if "citation_required" not in evidence:
            tc = output_spec.get("task_contract") if isinstance(output_spec.get("task_contract"), dict) else {}
            evidence["citation_required"] = bool(str(tc.get("evidence_mode") or "").strip().lower() == "required")
        if writing_mode == "evidence_bound":
            evidence["citation_required"] = True
        # Dynamic preset: trust quality_gates set upstream by normalize_minimal_spec
        # (which already gave synth's word range priority). Falling back to
        # gp/1200/2600 here was the second-tier leak that re-inflated short
        # forms (resume) even after minimal_spec preserved 350-700.
        if _is_dynamic_preset and quality.get("min_words") and quality.get("max_words"):
            min_words = int(quality["min_words"])
            max_words = int(quality["max_words"])
        elif _is_dynamic_preset:
            min_words = int(quality.get("min_words") or gp.get("min_words") or 400)
            max_words = int(quality.get("max_words") or gp.get("max_words") or 1200)
        else:
            min_words = int(quality.get("min_words") or gp.get("min_words") or 1200)
            max_words = int(quality.get("max_words") or gp.get("max_words") or 2600)
        if max_words < min_words:
            max_words = min_words + 600
        quality["min_words"] = min_words
        quality["max_words"] = max_words
        output["format"] = str(output.get("format") or "markdown").strip()
        deliverable = str(output.get("deliverable") or normalized_content_form or "").strip().lower()
        if normalized_content_form in {"report", "document", "document_scale", "prd", "brief"} or deliverable in {
            "report",
            "document",
            "document_scale",
            "prd",
            "brief",
        }:
            output["deliverable"] = "report" if normalized_content_form in {"report", "document", "document_scale", "prd"} else "brief"
        elif normalized_content_form == "plan" or deliverable == "plan":
            output["deliverable"] = "plan"
        else:
            output["deliverable"] = deliverable or "article"

        out["compose_policy"] = compose
        out["structure_contract"] = structure
        out["evidence_policy"] = evidence
        out["quality_gates"] = quality
        out["output_contract"] = output
        out["writing_mode"] = writing_mode
        
        # FIX: required_blocks must dictate absolute minimum section_count
        base_count = int(out.get("section_count") or 0)
        req_len = len(required_blocks)
        # Evidence-aware floor: when upstream supplied an explicit
        # evidence_strength_hint and it's thin, don't
        # pad a "report" up to 6 sections — let req_len drive section_count.
        evidence_hint_raw = compose.get("evidence_strength_hint")
        evidence_hint = int(evidence_hint_raw) if evidence_hint_raw is not None else -1
        thin_evidence = 0 <= evidence_hint < 4
        # Dynamic preset: synth's section_count / required_blocks is authoritative.
        # Forcing report->6 / brief->5 here was the third leak that turned a
        # 5-block resume contract into a 6-block report-shaped output.
        if _is_dynamic_preset:
            floor = 1
            out["section_count"] = max(floor, min(24, max(base_count, req_len)))
            return out
        if normalized_content_form == "report" and not thin_evidence:
            base_count = max(base_count, 6)
        elif normalized_content_form in {"brief", "document", "document_scale", "prd"} and not thin_evidence:
            base_count = max(base_count, 5)
        floor = 1 if thin_evidence else 4
        out["section_count"] = max(floor, min(24, max(base_count, req_len)))
        return out

    @staticmethod
    def _build_subject_context(output_spec: Dict[str, Any]) -> Dict[str, Any]:
        preset = output_spec.get("profile_preset") if isinstance(output_spec.get("profile_preset"), dict) else {}
        structure = preset.get("structure_contract") if isinstance(preset.get("structure_contract"), dict) else {}
        compose = preset.get("compose_policy") if isinstance(preset.get("compose_policy"), dict) else {}
        content_task_spec = output_spec.get("content_task_spec") if isinstance(output_spec.get("content_task_spec"), dict) else {}
        goal = content_task_spec.get("goal") if isinstance(content_task_spec.get("goal"), dict) else {}
        multimodal = output_spec.get("multimodal") if isinstance(output_spec.get("multimodal"), dict) else {}
        return {
            "content_form": str(compose.get("content_form") or "").strip(),
            "writing_mode": str(content_task_spec.get("writing_mode") or "").strip(),
            "required_sections": [str(x).strip() for x in list(structure.get("required_blocks") or output_spec.get("required_blocks") or []) if str(x).strip()][:8],
            "goal_outcome": str(goal.get("outcome") or "").strip(),
            "multimodal": multimodal,
        }

    @staticmethod
    def _build_multimodal_evidence_bundle(
        *,
        output_spec: Dict[str, Any],
        base_bundle: Dict[str, Any],
    ) -> Dict[str, Any]:
        bundle = dict(base_bundle or {}) if isinstance(base_bundle, dict) else {}
        multimodal = output_spec.get("multimodal") if isinstance(output_spec.get("multimodal"), dict) else {}
        if not multimodal:
            return bundle

        image_facts = multimodal.get("image_facts") if isinstance(multimodal.get("image_facts"), dict) else {}
        uploaded_assets = [dict(x) for x in list(multimodal.get("uploaded_assets") or []) if isinstance(x, dict)]
        subject_resolution = output_spec.get("subject_resolution") if isinstance(output_spec.get("subject_resolution"), dict) else {}
        results = [dict(x) for x in list(bundle.get("results") or []) if isinstance(x, dict)]
        topic = str(bundle.get("topic") or "").strip()
        entities = [str(x).strip() for x in list(bundle.get("entities") or []) if str(x).strip()]
        flow_steps = [str(x).strip() for x in list(bundle.get("flow_steps") or []) if str(x).strip()]
        requirements = [str(x).strip() for x in list(bundle.get("requirements") or []) if str(x).strip()]
        confirmed_facts = [str(x).strip() for x in list(bundle.get("confirmed_facts") or []) if str(x).strip()]
        open_questions = [str(x).strip() for x in list(bundle.get("open_questions") or []) if str(x).strip()]
        subject_candidates = [
            str(x).strip()
            for x in list(image_facts.get("subject_candidates") or image_facts.get("entities") or [])
            if str(x).strip()
        ]
        for item in list(image_facts.get("cross_image_facts") or [])[:12]:
            value = str(item or "").strip()
            if value and value not in confirmed_facts:
                confirmed_facts.append(value)
        for item in list(image_facts.get("uncertain") or [])[:12]:
            value = str(item or "").strip()
            if value and value not in open_questions:
                open_questions.append(value)

        for token in subject_candidates[:12]:
            value = str(token or "").strip()
            if value and value not in entities:
                entities.append(value)

        for item in list(image_facts.get("images") or [])[:8]:
            if not isinstance(item, dict):
                continue
            page_area = str(item.get("page_area") or "").strip()
            flow = str(item.get("flow_relationship") or "").strip()
            fields = [str(x).strip() for x in list(item.get("visible_fields") or [])[:5] if str(x).strip()]
            controls = [str(x).strip() for x in list(item.get("controls") or [])[:4] if str(x).strip()]
            if page_area and page_area not in requirements:
                requirements.append(page_area)
            if flow and flow not in flow_steps:
                flow_steps.append(flow)
            summary_parts = [part for part in [page_area, flow, " / ".join(fields), " / ".join(controls)] if part]
            if summary_parts:
                results.append(
                    {
                        "title": page_area or f"image_fact_{len(results)+1}",
                        "summary": "；".join(summary_parts),
                        "source": "multimodal_image_fact",
                        "structured_payload": {
                            key: value
                            for key, value in item.items()
                            if key
                            in {
                                "page_area",
                                "visible_fields",
                                "status_tags",
                                "flow_relationship",
                                "controls",
                            }
                        },
                    }
                )
            for fact in summary_parts[:3]:
                if fact and fact not in confirmed_facts:
                    confirmed_facts.append(fact)

        for asset in uploaded_assets[:8]:
            summary = str(asset.get("summary") or "").strip()
            if not summary:
                continue
            results.append(
                {
                    "title": str(asset.get("page_area") or asset.get("filename") or asset.get("asset_id") or "uploaded_image").strip(),
                    "summary": summary,
                    "source": "uploaded_image_asset",
                    "url": str(asset.get("signed_url") or asset.get("path") or "").strip(),
                }
            )

        if not topic:
            topic = str(subject_resolution.get("canonical_subject") or "").strip()
        if not topic and subject_candidates:
            topic = subject_candidates[0]
        if not topic:
            topic = str(multimodal.get("vision_summary") or "").strip()[:120]
        bundle["topic"] = topic
        bundle["entities"] = entities[:16]
        bundle["flow_steps"] = flow_steps[:16]
        bundle["requirements"] = requirements[:20]
        bundle["confirmed_facts"] = confirmed_facts[:20]
        bundle["open_questions"] = open_questions[:12]
        bundle["results"] = results[:24]
        return bundle

    @staticmethod
    def _build_document_tool_observations(
        *,
        output_spec: Dict[str, Any],
        base_observations: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        observations = [dict(x) for x in list(base_observations or []) if isinstance(x, dict)]
        documents = output_spec.get("documents") if isinstance(output_spec.get("documents"), dict) else {}
        parsed_documents = [dict(x) for x in list(documents.get("parsed_documents") or []) if isinstance(x, dict)]
        if not parsed_documents:
            return observations

        for item in parsed_documents[:10]:
            if str(item.get("parse_status") or "").strip() != "parsed":
                continue
            profile = dict(item.get("profile") or {})
            title = str(profile.get("title") or item.get("filename") or item.get("asset_id") or "uploaded_document").strip()
            source_url = str(item.get("source_url") or "").strip()
            summary = str(
                profile.get("active_context_brief")
                or profile.get("summary")
                or item.get("inline_markdown")
                or item.get("markdown")
                or ""
            ).strip()
            key_points = [str(x).strip() for x in list(profile.get("key_points") or []) if str(x).strip()]
            if key_points:
                summary = "\n".join([summary] + key_points[:4]) if summary else "；".join(key_points[:4])
            if not summary:
                continue
            observation = {
                "tool": "uploaded_document",
                "query": title,
                "summary": summary[:2000],
                "sources": [{"title": title, "url": source_url}] if source_url else [],
                "artifacts": [{"type": "document", "url": source_url, "caption": title}] if source_url else [],
            }
            observations.append(observation)
        return observations[:24]

    @staticmethod
    def _document_markdown_evidence_items(markdown: str, *, source_url: str, title: str, limit: int = 8) -> List[Dict[str, Any]]:
        text = str(markdown or "").strip()
        if not text:
            return []
        chunks: List[Dict[str, Any]] = []
        heading = title
        current: List[str] = []
        for raw_line in text.splitlines():
            line = str(raw_line or "").rstrip()
            if line.startswith("## "):
                if current:
                    body = "\n".join(current).strip()
                    if body:
                        chunks.append({"title": heading, "summary": body[:2000], "url": source_url, "source": "uploaded_document_markdown"})
                heading = line[3:].strip() or title
                current = []
                continue
            if line:
                current.append(line)
        if current:
            body = "\n".join(current).strip()
            if body:
                chunks.append({"title": heading, "summary": body[:2000], "url": source_url, "source": "uploaded_document_markdown"})
        return chunks[:limit]

    @classmethod
    def _build_document_evidence_bundle(
        cls,
        *,
        output_spec: Dict[str, Any],
        base_bundle: Dict[str, Any],
    ) -> Dict[str, Any]:
        bundle = dict(base_bundle or {}) if isinstance(base_bundle, dict) else {}
        documents = output_spec.get("documents") if isinstance(output_spec.get("documents"), dict) else {}
        parsed_documents = [dict(x) for x in list(documents.get("parsed_documents") or []) if isinstance(x, dict)]
        if not parsed_documents:
            return bundle

        results = [dict(x) for x in list(bundle.get("results") or []) if isinstance(x, dict)]
        topic = str(bundle.get("topic") or "").strip()
        entities = [str(x).strip() for x in list(bundle.get("entities") or []) if str(x).strip()]
        flow_steps = [str(x).strip() for x in list(bundle.get("flow_steps") or []) if str(x).strip()]
        requirements = [str(x).strip() for x in list(bundle.get("requirements") or []) if str(x).strip()]
        confirmed_facts = [str(x).strip() for x in list(bundle.get("confirmed_facts") or []) if str(x).strip()]
        open_questions = [str(x).strip() for x in list(bundle.get("open_questions") or []) if str(x).strip()]
        document_result_groups: List[List[Dict[str, Any]]] = []
        document_fact_groups: List[List[str]] = []

        for item in parsed_documents[:10]:
            if str(item.get("parse_status") or "").strip() != "parsed":
                continue
            profile = dict(item.get("profile") or {})
            title = str(profile.get("title") or item.get("filename") or item.get("asset_id") or "uploaded_document").strip()
            source_url = str(item.get("source_url") or "").strip()
            summary = str(profile.get("summary") or profile.get("active_context_brief") or "").strip()
            document_results: List[Dict[str, Any]] = []
            document_facts: List[str] = []
            if summary:
                document_results.append(
                    {
                        "title": title,
                        "summary": summary[:2000],
                        "url": source_url,
                        "source": "uploaded_document_profile",
                    }
                )
                document_facts.append(summary)

            for token in list(profile.get("subject_candidates") or [])[:6]:
                value = str(token or "").strip()
                if value and value not in entities:
                    entities.append(value)
            for token in list(profile.get("section_outline") or [])[:8]:
                value = str(token or "").strip()
                if value and value not in requirements:
                    requirements.append(value)
            for token in list(profile.get("key_points") or [])[:10]:
                value = str(token or "").strip()
                if value and value not in document_facts:
                    document_facts.append(value)

            for brief in list(item.get("chunk_briefs") or [])[:8]:
                if not isinstance(brief, dict):
                    continue
                brief_summary = str(brief.get("summary") or "").strip()
                brief_title = ""
                signals = [str(x).strip() for x in list(brief.get("section_signals") or []) if str(x).strip()]
                if signals:
                    brief_title = " / ".join(signals[:2])
                if brief_summary:
                    document_results.append(
                        {
                            "title": brief_title or title,
                            "summary": brief_summary[:2000],
                            "url": source_url,
                            "source": "uploaded_document_chunk",
                        }
                    )
                for token in signals[:4]:
                    if token and token not in flow_steps:
                        flow_steps.append(token)
                for token in list(brief.get("key_points") or [])[:6]:
                    value = str(token or "").strip()
                    if value and value not in document_facts:
                        document_facts.append(value)

            markdown = str(item.get("markdown") or "").strip()
            for result in cls._document_markdown_evidence_items(markdown, source_url=source_url, title=title, limit=10):
                document_results.append(result)
            if document_results:
                document_result_groups.append(document_results)
            if document_facts:
                document_fact_groups.append(document_facts)

        results.extend(round_robin_take(document_result_groups, limit=max(0, 64 - len(results))))
        selected_document_facts = round_robin_take(document_fact_groups, limit=max(0, 48 - len(confirmed_facts)))
        for fact in selected_document_facts:
            if fact not in confirmed_facts:
                confirmed_facts.append(fact)

        if not topic:
            topic = str(documents.get("active_document_context") or output_spec.get("active_document_context") or "").strip()[:160]
        bundle["topic"] = topic
        bundle["entities"] = entities[:20]
        bundle["flow_steps"] = flow_steps[:20]
        bundle["requirements"] = requirements[:20]
        bundle["confirmed_facts"] = confirmed_facts[:48]
        bundle["open_questions"] = open_questions[:12]
        bundle["results"] = results[:64]
        return bundle

    @staticmethod
    def _compact_structured_evidence(value: Any, *, limit: int = 2400) -> str:
        if value is None:
            return ""
        try:
            text = json.dumps(value, ensure_ascii=False, default=str, indent=2)
        except Exception:
            text = str(value)
        text = text.strip()
        if len(text) <= limit:
            return text
        return text[:limit].rstrip() + "\n...<truncated>"

    @classmethod
    def _build_graph_artifact_evidence_bundle(
        cls,
        *,
        output_spec: Dict[str, Any],
        base_bundle: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Promote graph node artifacts into the normal evidence bundle.

        Graph execution already passes upstream node outputs through
        ``predecessor_artifacts`` / ``input_artifacts``. The writer evidence
        contract, however, is ``evidence_bundle``. This bridge keeps graph
        outputs inside the existing grounding path instead of inventing a
        separate writer/reviewer flow.
        """
        bundle = dict(base_bundle or {}) if isinstance(base_bundle, dict) else {}
        artifact_buckets: List[Tuple[str, Dict[str, Any]]] = []
        for bucket_name in ("predecessor_artifacts", "input_artifacts", "graph_artifacts"):
            bucket = output_spec.get(bucket_name) if isinstance(output_spec.get(bucket_name), dict) else {}
            if bucket:
                artifact_buckets.append((bucket_name, bucket))
        if not artifact_buckets:
            return bundle

        results = [dict(x) for x in list(bundle.get("results") or []) if isinstance(x, dict)]
        confirmed_facts = [str(x).strip() for x in list(bundle.get("confirmed_facts") or []) if str(x).strip()]
        entities = [str(x).strip() for x in list(bundle.get("entities") or []) if str(x).strip()]
        requirements = [str(x).strip() for x in list(bundle.get("requirements") or []) if str(x).strip()]

        seen_results = {
            (str(item.get("source") or ""), str(item.get("title") or ""))
            for item in results
            if isinstance(item, dict)
        }
        seen_node_keys: set[str] = set()
        added = 0
        for bucket_name, bucket in artifact_buckets:
            for node_id, artifact in bucket.items():
                if not isinstance(artifact, dict):
                    continue
                node_key = str(node_id or "").strip() or "graph_node"
                if node_key in seen_node_keys:
                    continue
                result = project_graph_artifact_result(
                    node_id=node_key,
                    artifact_bucket=bucket_name,
                    artifact=artifact,
                )
                if not result:
                    continue
                title = str(result.get("title") or "")
                source = str(result.get("source") or "")
                dedupe_key = (source, title)
                if dedupe_key in seen_results:
                    continue
                seen_results.add(dedupe_key)
                seen_node_keys.add(node_key)
                summary = str(result.get("summary") or "").strip()
                if not summary:
                    continue
                results.append(result)
                if summary not in confirmed_facts:
                    confirmed_facts.append(summary)
                for name_key in ("name", "title"):
                    value = artifact.get(name_key)
                    if isinstance(value, str) and value.strip() and value.strip() not in entities:
                        entities.append(value.strip())
                added += 1
                if added >= 24:
                    break
            if added >= 24:
                break

        if added <= 0:
            return bundle

        if "Use graph node artifacts as grounded evidence for generated answers." not in requirements:
            requirements.append("Use graph node artifacts as grounded evidence for generated answers.")
        bundle["results"] = results[:48]
        bundle["confirmed_facts"] = confirmed_facts[:48]
        bundle["entities"] = entities[:24]
        bundle["requirements"] = requirements[:24]
        bundle["graph_artifact_evidence_count"] = added
        return bundle

    @staticmethod
    def _inject_agreement_template(*, output_spec: Dict[str, Any], bundle: Dict[str, Any]) -> Dict[str, Any]:
        """For agreement mode, inject the full uploaded document markdown as a
        template/draft so that the outline planner extracts clause structure from
        it and the section writer uses it as baseline content to modify."""
        bundle = dict(bundle or {})
        documents = output_spec.get("documents") if isinstance(output_spec.get("documents"), dict) else {}
        parsed_documents = [dict(x) for x in list(documents.get("parsed_documents") or []) if isinstance(x, dict)]
        if not parsed_documents:
            return bundle
        # Use the first successfully parsed document as the agreement template.
        for item in parsed_documents[:3]:
            if str(item.get("parse_status") or "").strip() != "parsed":
                continue
            markdown = str(item.get("markdown") or "").strip()
            if not markdown:
                continue
            title = str(
                (item.get("profile") or {}).get("title")
                or item.get("filename")
                or "uploaded_agreement"
            ).strip()
            # Insert as a high-priority "template" result at the front of the bundle.
            template_result = {
                "title": f"[协议底稿] {title}",
                "summary": markdown[:8000],
                "url": str(item.get("source_url") or "").strip(),
                "source": "agreement_template",
            }
            results = list(bundle.get("results") or [])
            results.insert(0, template_result)
            bundle["results"] = results[:40]
            bundle["agreement_template_markdown"] = markdown[:12000]
            break
        return bundle

    TRANSLATABLE_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".txt", ".md"}

    @staticmethod
    def _inject_translation_source(*, output_spec: Dict[str, Any], bundle: Dict[str, Any]) -> Dict[str, Any]:
        """For translation mode, inject the uploaded document's full markdown
        as the translation source material."""
        import os
        bundle = dict(bundle or {})
        documents = output_spec.get("documents") if isinstance(output_spec.get("documents"), dict) else {}
        parsed_documents = [dict(x) for x in list(documents.get("parsed_documents") or []) if isinstance(x, dict)]
        if not parsed_documents:
            return bundle
        for item in parsed_documents[:3]:
            markdown = str(item.get("markdown") or "").strip()
            filename = str(item.get("filename") or "").strip()
            ext = os.path.splitext(filename.lower())[1] if filename else ""
            parse_status = str(item.get("parse_status") or "").strip()
            source_object_path = str(item.get("object_path") or "").strip()
            source_url = str(item.get("source_url") or item.get("signed_url") or item.get("url") or "").strip()
            binary_translatable = ext in {".docx", ".xlsx"}
            # PDF/TXT/MD 这类文本翻译仍要求成功抽取 markdown；DOCX/XLSX 允许在
            # 解析失败时直接回退到原始二进制下载地址，走原位翻译链路。
            if binary_translatable:
                if not source_object_path and not source_url:
                    continue
            else:
                if parse_status != "parsed" or not markdown:
                    continue
            if not filename:
                continue
            bundle["translation_source_markdown"] = markdown
            bundle["translation_source_filename"] = filename
            bundle["translation_source_ext"] = ext
            # 保留 OSS object_path 与 signed url，原位翻译需要下载原始 .docx 字节。
            bundle["translation_source_object_path"] = source_object_path
            bundle["translation_source_url"] = source_url
            bundle["translation_source_content_type"] = str(item.get("content_type") or "").strip()
            break
        return bundle

    @staticmethod
    def _resolve_subject_generation_gate(
        *,
        user_query: str,
        subject_resolution: Dict[str, Any],
        tool_observations: List[Dict[str, Any]],
        evidence_bundle: Dict[str, Any],
        channel: str = "",
        audience: str = "",
        execution_kind: str = "",
        schema_category: str = "",
    ) -> Dict[str, Any]:
        # Execution-type tasks (browser automation, code,
        # file transforms) deliver results that are inherently "about" a
        # target the user already specified (a URL, a file, a system).
        # The subject-resolution gate is designed for topic writing — it
        # treats the URL's "https" token as an ambiguous subject label
        # and demands the user clarify, which produces nonsense tails
        # like "can't uniquely identify 'https'" on execution reports.
        # Hard-disable the gate for non-content execution kinds.
        ek = str(execution_kind or "").strip().lower()
        if ek and ek != "content":
            return {"action": "proceed", "evidence_strength": 0, "gate_skipped": f"execution_kind={ek}"}
        status = str(subject_resolution.get("status") or "").strip().lower()
        selection_confidence = max(0.0, min(1.0, float(subject_resolution.get("selection_confidence") or 0.0)))
        canonical_subject = strip_visual_or_production_clauses(
            str(subject_resolution.get("canonical_subject") or "")
        ).strip()
        candidate_subjects = []
        for item in list(subject_resolution.get("candidate_subjects") or []):
            token = strip_visual_or_production_clauses(str(item or "")).strip()
            if token and token not in candidate_subjects:
                candidate_subjects.append(token)
        supporting_facts = [
            strip_visual_or_production_clauses(str(item or "")).strip()
            for item in list(subject_resolution.get("supporting_facts") or [])
            if strip_visual_or_production_clauses(str(item or "")).strip()
        ]
        observation_count = len([item for item in list(tool_observations or []) if isinstance(item, dict)])
        evidence_results = len([item for item in list((evidence_bundle or {}).get("results") or []) if isinstance(item, dict)])
        confirmed_facts = len(
            [item for item in list((evidence_bundle or {}).get("confirmed_facts") or []) if str(item or "").strip()]
        )
        evidence_strength = observation_count + evidence_results + confirmed_facts + len(supporting_facts)
        if canonical_subject and (
            status == "resolved_single_subject"
            or selection_confidence >= 0.55
        ):
            return {"action": "proceed", "evidence_strength": evidence_strength}

        if len(candidate_subjects) >= 2 and CandidateAnalyzer.are_synonymous(candidate_subjects):
            return {"action": "proceed", "evidence_strength": evidence_strength}

        subject_label = ToolWriterEngineComposeSkill._extract_ambiguous_subject_label(
            user_query=user_query,
            fallback=candidate_subjects[0] if candidate_subjects else "",
        )
        if len(candidate_subjects) >= 2 and evidence_strength >= max(2, len(candidate_subjects[:3])):
            return {
                "action": "disambiguate",
                "evidence_strength": evidence_strength,
                "body_user_goal": ToolWriterEngineComposeSkill._build_disambiguation_goal(
                    subject_label=subject_label,
                    candidate_subjects=candidate_subjects,
                ),
            }
        return {
            "action": "clarify",
            "evidence_strength": evidence_strength,
            "message": ToolWriterEngineComposeSkill._build_subject_clarification_message(
                user_query=user_query,
                subject_label=subject_label,
                candidate_subjects=candidate_subjects,
            ),
        }

    @staticmethod
    def _resolve_strict_grounding_blocker(
        *,
        output_spec: Dict[str, Any],
        user_query: str,
        tool_observations: List[Dict[str, Any]],
        evidence_bundle: Dict[str, Any],
    ) -> str:
        effective = output_spec.get("effective_policy") if isinstance(output_spec.get("effective_policy"), dict) else {}
        compose = effective.get("compose_policy") if isinstance(effective.get("compose_policy"), dict) else {}
        research = effective.get("research_policy") if isinstance(effective.get("research_policy"), dict) else {}
        strictness = str(compose.get("grounding_strictness") or "").strip().lower()
        if strictness != "strict":
            return ""
        must_tools = [str(x).strip() for x in list(research.get("must_use_tools") or []) if str(x).strip()]
        preferred_tools = [str(x).strip() for x in list(research.get("preferred_tools") or []) if str(x).strip()]
        scope = str(research.get("research_scope") or "").strip().lower()
        requires_search = bool(scope in {"internal_kb", "public_web", "mixed"} or must_tools or preferred_tools)
        if not requires_search:
            return ""
        evidence_count = 0
        evidence_count += len([x for x in list(tool_observations or []) if isinstance(x, dict)])
        evidence_count += len([x for x in list((evidence_bundle or {}).get("results") or []) if isinstance(x, dict)])
        evidence_count += len([x for x in list((evidence_bundle or {}).get("confirmed_facts") or []) if str(x or "").strip()])
        if evidence_count > 0:
            return ""
        is_zh = bool(re.search(r"[\u4e00-\u9fff]", str(user_query or "")))
        if is_zh:
            return "未检索到足够可依据的资料。由于你要求必须基于检索结果且不要编造，我不能在缺少可靠资料的情况下继续生成正文。"
        return "I could not find enough grounded evidence. Because you asked me to rely on search results and not invent facts, I cannot continue drafting without reliable source material."

    @staticmethod
    def _extract_ambiguous_subject_label(*, user_query: str, fallback: str = "") -> str:
        text = str(user_query or "").strip()
        for pattern in [r"“([^”]{1,40})”", r"\"([^\"]{1,40})\""]:
            m = re.search(pattern, text)
            if m:
                return str(m.group(1) or "").strip()
        token = re.findall(r"[A-Za-z][A-Za-z0-9._\-]{1,24}", text)
        if token:
            return str(token[0] or "").strip()
        if fallback:
            return str(fallback or "").strip()
        return "该主题"

    @staticmethod
    def _build_disambiguation_goal(*, subject_label: str, candidate_subjects: List[str]) -> str:
        label = str(subject_label or "该主题").strip()
        candidates = [str(item or "").strip() for item in list(candidate_subjects or []) if str(item or "").strip()]
        candidate_text = "、".join(candidates[:4]) if candidates else "最相关的几个候选对象"
        return (
            f"不要把“{label}”写成唯一确定对象。先说明它在当前上下文里存在多种常见含义，"
            f"重点解释这些候选：{candidate_text}。分别概括每个候选的核心概念、适用场景和区分线索，"
            "最后明确告诉读者若要继续深入，需要补充哪些上下文。全文保持消歧说明写法，不要假装已经唯一识别。"
        )

    @staticmethod
    def _build_subject_clarification_message(
        *,
        user_query: str,
        subject_label: str,
        candidate_subjects: List[str],
    ) -> str:
        zh = contains_cjk(user_query)
        label = str(subject_label or "该主题").strip()
        candidates = [str(item or "").strip() for item in list(candidate_subjects or []) if str(item or "").strip()]
        if zh:
            lines = [f"当前还不能唯一确定你说的“{label}”具体指哪一个对象。"]
            if candidates:
                lines.append("我目前识别到的候选有：")
                for idx, item in enumerate(candidates[:4], start=1):
                    lines.append(f"{idx}. {item}")
            lines.append("请补充一句上下文，或直接告诉我你指的是哪一个，我再按原要求继续生成。")
            return "\n".join(lines)
        lines = [f"I can't uniquely identify what '{label}' refers to yet."]
        if candidates:
            lines.append("Current likely candidates:")
            for idx, item in enumerate(candidates[:4], start=1):
                lines.append(f"{idx}. {item}")
        lines.append("Please add one line of context or tell me which one you mean, and I'll continue with the original writing request.")
        return "\n".join(lines)

    @staticmethod
    def _extract_user_query(context: SkillContext) -> str:
        inherited = ""
        if isinstance(context.output_spec, dict):
            inherited = str(context.output_spec.get("inherited_user_request") or "").strip()
        if inherited:
            return inherited
        for msg in reversed(context.messages or []):
            if msg.role == Role.USER and isinstance(msg.content, str):
                return msg.content.strip()
        return ""

    @staticmethod
    def _augment_body_goal_with_data_flow(
        *,
        body_user_goal: str,
        raw_user_query: str,
        upstream_artifacts: Dict[str, Any],
        node_meta: Dict[str, Any],
    ) -> str:
        """Append the cross-node data-flow context block to ``body_user_goal``.

        The compose LLM already has ``body_user_goal`` describing "how to
        write". This augmentation tells it "what came in from upstream and
        what's waiting downstream" so content can be grounded in real data
        rather than templated from thin air.

        Empty-upstream flag: when this node declared upstream deps but
        every value is empty/falsy, we *explicitly* say so — a compose
        LLM should surface "insufficient upstream data" rather than
        fabricate placeholder sections.
        """
        lines: List[str] = []

        trimmed_query = str(raw_user_query or "").strip()
        # Only include the user's original request when the body_user_goal
        # above didn't already quote it verbatim — avoids doubling the
        # same text into the prompt.
        if trimmed_query and trimmed_query not in (body_user_goal or ""):
            lines.append(f"【用户最终要的（所有节点共享的原始请求）】\n{trimmed_query}")

        upstream_pairs: List[Tuple[str, Any]] = []
        if isinstance(upstream_artifacts, dict):
            for k, v in upstream_artifacts.items():
                key = str(k or "").strip()
                if not key or key.startswith("_"):
                    continue
                if key in ("browser_receipt", "skill_state", "skill_finalize", "answer", "graph_node_id"):
                    continue
                upstream_pairs.append((key, v))

        def _value_looks_empty(val: Any) -> bool:
            if val is None:
                return True
            if isinstance(val, str):
                s = val.strip().lower()
                return s in ("", "null", "none", "n/a", "undefined", "待确认", "tbd")
            if isinstance(val, (list, dict)):
                return not val
            return False

        if upstream_pairs:
            cleaned_upstream_pairs: List[Tuple[str, Any]] = []
            stripped_external_raw_count = 0
            for key, val in upstream_pairs:
                cleaned_val, removed_count = strip_external_web_raw(val)
                stripped_external_raw_count += removed_count
                if _value_looks_empty(cleaned_val):
                    continue
                cleaned_upstream_pairs.append((key, cleaned_val))

            all_empty = not cleaned_upstream_pairs or all(_value_looks_empty(v) for _k, v in cleaned_upstream_pairs)
            if all_empty:
                lines.append(
                    "【上游节点产出】\n"
                    "⚠ 上游节点声明了这些产物键，但**值全是空的**。"
                    "不要在空数据上编写内容 —— 要在正文里明确指出"
                    "\"上游未成功抓取数据，无法给出具体数字\"，必要时让用户感知。\n"
                    + "\n".join(f"  - {k}: （空）" for k, _ in upstream_pairs[:10])
                )
            else:
                rendered: List[str] = []
                for key, val in cleaned_upstream_pairs[:12]:
                    try:
                        val_json = json.dumps(val, ensure_ascii=False)
                    except Exception:
                        val_json = str(val)
                    if len(val_json) > 1200:
                        val_json = val_json[:1200] + "...<truncated>"
                    rendered.append(f"  - {key}: {val_json}")
                if stripped_external_raw_count:
                    rendered.append(f"  - external_search_raw_filtered: {stripped_external_raw_count}")
                lines.append(
                    "【上游节点产出（含具体值，作为写作依据）】\n"
                    + "\n".join(rendered)
                )

        consumers = node_meta.get("downstream_consumers") if isinstance(node_meta, dict) else None
        if isinstance(consumers, list) and consumers:
            consumer_lines: List[str] = []
            for c in consumers:
                if not isinstance(c, dict):
                    continue
                node_id = str(c.get("node_id") or "").strip()
                obj = str(c.get("objective") or "").strip()
                reqs = [str(x) for x in (c.get("required_inputs") or []) if str(x).strip()]
                bits: List[str] = []
                if node_id:
                    bits.append(f"`{node_id}`")
                if obj:
                    bits.append(f"目标: {obj}")
                if reqs:
                    bits.append(f"需要的 artifact: {', '.join(reqs[:6])}")
                if bits:
                    consumer_lines.append("  - " + " | ".join(bits))
            if consumer_lines:
                lines.append(
                    "【下游节点在等你交的】(塑形你的产出，让下游能直接拿来用)\n"
                    + "\n".join(consumer_lines)
                )

        if not lines:
            return body_user_goal
        return (body_user_goal or "") + "\n\n" + "\n\n".join(lines)

    @staticmethod
    def _build_body_user_goal(output_spec: Dict[str, Any], fallback: str) -> str:
        subject_resolution = output_spec.get("subject_resolution") if isinstance(output_spec.get("subject_resolution"), dict) else {}
        subject_hint = strip_visual_or_production_clauses(str(subject_resolution.get("article_goal_hint") or ""))
        canonical_subject = strip_visual_or_production_clauses(str(subject_resolution.get("canonical_subject") or ""))
        supporting_facts = [
            strip_visual_or_production_clauses(str(x))
            for x in list(subject_resolution.get("supporting_facts") or [])
            if strip_visual_or_production_clauses(str(x))
        ][:3]
        content_task_spec = output_spec.get("content_task_spec") if isinstance(output_spec.get("content_task_spec"), dict) else {}
        writing_mode = ToolWriterEngineComposeSkill._normalize_writing_mode(content_task_spec.get("writing_mode"))
        goal = dict(content_task_spec.get("goal") or {})
        publish_narrative = dict(content_task_spec.get("publish_narrative") or {})
        outcome = strip_visual_or_production_clauses(str(goal.get("outcome") or ""))
        preset = output_spec.get("profile_preset") if isinstance(output_spec.get("profile_preset"), dict) else {}
        structure = dict(preset.get("structure_contract") or {})
        compose = dict(preset.get("compose_policy") or {})
        output_contract = dict(preset.get("output_contract") or {})
        required_blocks = [str(x).strip() for x in list(structure.get("required_blocks") or output_spec.get("required_blocks") or []) if str(x).strip()]
        reader_problem = strip_visual_or_production_clauses(str(publish_narrative.get("reader_problem") or ""))
        narrative_goal = strip_visual_or_production_clauses(str(publish_narrative.get("narrative_goal") or ""))
        opening_intent = strip_visual_or_production_clauses(str(publish_narrative.get("opening_intent") or ""))
        closing_intent = strip_visual_or_production_clauses(str(publish_narrative.get("closing_intent") or ""))
        content_form = str(compose.get("content_form") or output_contract.get("deliverable") or "").strip().lower()
        base = ToolWriterEngineComposeSkill._body_base_instruction(output_spec, content_form)
        if reader_problem or narrative_goal:
            parts = [base]
            if writing_mode == "evidence_bound":
                parts.append("仅可基于已确认事实写作，证据不足时必须明确写为待确认或建议项")
            elif writing_mode == "hybrid":
                parts.append("正文以事实为主，允许有限建议补充，但不要把推断写成既定事实")
            if canonical_subject:
                parts.append(f"全文围绕“{canonical_subject}”展开")
            if supporting_facts:
                parts.append(f"优先锚定这些事实：{'；'.join(supporting_facts)}")
            if reader_problem:
                parts.append(f"围绕这个真实问题推进：{reader_problem}")
            if narrative_goal:
                parts.append(f"文章目标：{narrative_goal}")
            if opening_intent:
                parts.append(f"开头要求：{opening_intent}")
            if closing_intent:
                parts.append(f"结尾要求：{closing_intent}")
            if required_blocks:
                parts.append(f"正文覆盖这些内容块：{'、'.join(required_blocks[:8])}")
            return "。".join([p for p in parts if p]).strip("。 ") + "。"
        if canonical_subject and required_blocks:
            base_parts = [f"围绕“{canonical_subject}”完成当前文档"]
            if writing_mode == "evidence_bound":
                base_parts.append("仅可基于已确认事实写作，证据不足时必须明确写为待确认或建议项")
            if supporting_facts:
                base_parts.append(f"优先锚定这些事实：{'；'.join(supporting_facts)}")
            base_parts.append(f"正文覆盖这些内容块：{'、'.join(required_blocks[:8])}")
            return "。".join(base_parts).strip("。 ") + "。"
        if canonical_subject:
            if supporting_facts:
                return f"围绕“{canonical_subject}”完成当前文档，并优先锚定这些事实：{'；'.join(supporting_facts)}。"
            return f"围绕“{canonical_subject}”完成当前文档，保持所有章节和论证都服务于这个核心对象。"
        if subject_hint and required_blocks:
            return f"{subject_hint}。正文覆盖这些内容块：{'、'.join(required_blocks[:8])}。"
        if subject_hint:
            return subject_hint
        if outcome and required_blocks:
            return f"{outcome}。正文覆盖这些内容块：{'、'.join(required_blocks[:8])}。"
        if outcome:
            return outcome
        compose_profile = output_spec.get("compose_profile") if isinstance(output_spec.get("compose_profile"), dict) else {}
        intent_statement = strip_visual_or_production_clauses(str(compose_profile.get("intent_statement") or ""))
        if intent_statement and required_blocks:
            return f"{intent_statement}。正文覆盖这些内容块：{'、'.join(required_blocks[:8])}。"
        if intent_statement:
            return intent_statement
        return strip_visual_or_production_clauses(fallback)

    @staticmethod
    def _build_title_hint(
        *,
        output_spec: Dict[str, Any],
        canonical_subject: str,
        language: str,
        user_query: str = "",
    ) -> str:
        explicit_title = strip_visual_or_production_clauses(
            str((output_spec or {}).get("explicit_title_block") or "")
        ).strip()
        if explicit_title:
            return explicit_title
        subject = ToolWriterEngineComposeSkill._localize_subject_for_title(
            output_spec=output_spec,
            canonical_subject=canonical_subject,
            language=language,
            user_query=user_query,
        )
        if not subject:
            return ""
        content_task_spec = output_spec.get("content_task_spec") if isinstance(output_spec.get("content_task_spec"), dict) else {}
        writing_mode = ToolWriterEngineComposeSkill._normalize_writing_mode(content_task_spec.get("writing_mode"))
        if writing_mode == "creative":
            return ""
        preset = output_spec.get("profile_preset") if isinstance(output_spec.get("profile_preset"), dict) else {}
        compose = preset.get("compose_policy") if isinstance(preset.get("compose_policy"), dict) else {}
        output_contract = preset.get("output_contract") if isinstance(preset.get("output_contract"), dict) else {}
        deliverable = str(
            output_contract.get("deliverable")
            or compose.get("content_form")
            or output_spec.get("content_form")
            or "document"
        ).strip().lower()
        if deliverable in {"article", "post"}:
            label = "文章" if language == "zh" else "Article"
        elif deliverable in {"brief"}:
            label = "简报" if language == "zh" else "Brief"
        elif deliverable in {"plan"}:
            label = "方案" if language == "zh" else "Plan"
        else:
            label = "文档" if language == "zh" else "Document"
        if label in subject:
            return subject
        return f"{subject} {label}".strip()

    @staticmethod
    def _localize_subject_for_title(
        *,
        output_spec: Dict[str, Any],
        canonical_subject: str,
        language: str,
        user_query: str = "",
    ) -> str:
        subject = strip_visual_or_production_clauses(str(canonical_subject or "")).strip()
        if not subject:
            return ""
        if language != "zh" or contains_cjk(subject):
            return subject

        multimodal = output_spec.get("multimodal") if isinstance(output_spec.get("multimodal"), dict) else {}
        image_facts = multimodal.get("image_facts") if isinstance(multimodal.get("image_facts"), dict) else {}
        candidates: List[str] = []
        for token in list(image_facts.get("subject_candidates") or []) + list(image_facts.get("entities") or []):
            value = str(token or "").strip()
            if value and contains_cjk(value) and value not in candidates:
                candidates.append(value)
        strong_candidates = [item for item in candidates if any(marker in item for marker in ("系统", "平台", "工作台", "体系"))]
        if strong_candidates:
            return strong_candidates[0]
        for token in list(image_facts.get("page_titles") or []) + list(image_facts.get("ui_terms") or []):
            value = str(token or "").strip()
            if value and contains_cjk(value) and value not in candidates:
                candidates.append(value)
        if candidates:
            return candidates[0]
        return subject

    @staticmethod
    def _strip_visual_style_axes(style_markdown: str) -> str:
        text = str(style_markdown or "").strip()
        if not text:
            return ""
        blocked_prefixes = (
            "- visual_type_mix:",
            "- required_visual_total:",
            "- visual_roles:",
        )
        kept = []
        for raw in text.splitlines():
            line = str(raw or "")
            stripped = line.strip().lower()
            if any(stripped.startswith(prefix) for prefix in blocked_prefixes):
                continue
            kept.append(line)
        return "\n".join(kept).strip()

    @staticmethod
    def _sanitize_body_style_markdown(style_markdown: str) -> str:
        text = str(style_markdown or "").strip()
        if not text:
            return ""

        if text.startswith("---"):
            lines = text.splitlines()
            end = None
            for idx in range(1, len(lines)):
                if lines[idx].strip() == "---":
                    end = idx
                    break
            if end is not None:
                front = "\n".join(lines[1:end])
                body = "\n".join(lines[end + 1 :]).lstrip()
                try:
                    meta = yaml.safe_load(front) or {}
                except Exception:
                    meta = {}
                if isinstance(meta, dict):
                    style_contract = meta.get("style_contract")
                    if isinstance(style_contract, dict):
                        style_contract = dict(style_contract)
                        style_contract.pop("visual_policy", None)
                        meta["style_contract"] = style_contract
                    meta.pop("visual_policy", None)
                front_clean = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip() if isinstance(meta, dict) and meta else ""
                text = (f"---\n{front_clean}\n---\n\n{body}" if front_clean else body).strip()

        lines = text.splitlines()
        kept: list[str] = []
        skip_section = False
        in_visual_block = False
        for raw in lines:
            line = str(raw or "")
            stripped = line.strip()
            lowered = stripped.lower()

            if lowered.startswith("[visual:"):
                in_visual_block = True
                continue
            if lowered == "[/visual]":
                in_visual_block = False
                continue
            if in_visual_block:
                continue

            if re.match(r"^#{1,6}\s+", stripped):
                title = re.sub(r"^#{1,6}\s+", "", stripped).strip().lower()
                if title in {"visual spec format", "visual specs", "image guidance", "image generation"}:
                    skip_section = True
                    continue
                skip_section = False
            if skip_section:
                continue
            if any(token in lowered for token in ["visual_spec_format:", "include_infographic_blocks:", "image_render_enabled:"]):
                continue
            kept.append(line)
        text = strip_visual_placeholder_directives("\n".join(kept).strip())
        return ToolWriterEngineComposeSkill._strip_visual_style_axes(text)

    async def run_stream(self, context: SkillContext) -> AsyncIterator[Dict[str, Any]]:
        output_spec = dict(context.output_spec or {})
        payload = dict(context.payload or {})
        raw_user_query = self._extract_user_query(context)

        strategy = self._build_strategy(output_spec)
        strategy = self._attach_section_arguments(strategy)
        strategy = self._ensure_runtime_contract(strategy, output_spec)
        strategy["_operation_scope"] = str(
            output_spec.get("current_task_node_id") or output_spec.get("request_id") or "writer"
        ).strip()
        # Keep debug output aligned with the finalized runtime contract.
        output_spec["required_blocks"] = list(
            ((strategy.get("structure_contract") or {}).get("required_blocks") or [])
        )
        route = self._decide_execution_mode(strategy=strategy, output_spec=output_spec, user_query=raw_user_query)
        resolved_mode = str(route.get("mode") or "direct_compose")
        strategy["mode"] = (
            "sectional_compose"
            if resolved_mode in {"sectional_compose", "document_scale_compose"}
            else "direct_compose"
        )
        # Merge delivery-level flags (e.g. agreement mode) from the upstream compose_strategy
        # OR detect agreement type directly from output_spec (graph orchestrator path).
        delivery_compose = payload.get("compose_strategy") if isinstance(payload.get("compose_strategy"), dict) else {}
        delivery_mode = str(delivery_compose.get("mode") or "").strip().lower()
        if delivery_mode != "agreement_clauses":
            # Fallback: detect agreement from output_spec deliverable_type / task_contract
            # (graph orchestrator does NOT call build_delivery_profile, so compose_strategy is empty)
            _gc = output_spec.get("goal_contract") if isinstance(output_spec.get("goal_contract"), dict) else {}
            _tc = output_spec.get("task_contract") if isinstance(output_spec.get("task_contract"), dict) else {}
            _dtype = str(
                _gc.get("deliverable_type")
                or _tc.get("deliverable_mode")
                or _tc.get("selected_mode")
                or ""
            ).strip().lower()
            if _dtype in {"agreement", "contract", "protocol", "mou", "nda", "terms"}:
                delivery_mode = "agreement_clauses"
            elif _dtype in {"translation", "translate"}:
                delivery_mode = "translation"
        if delivery_mode == "translation":
            strategy["mode"] = "translation"
            strategy["skip_toc"] = True
            strategy["skip_visuals"] = True
            strategy["visual_policy"] = {
                "min_visuals_per_report": 0,
                "max_visuals_per_report": 0,
                "min_infographics_per_report": 0,
                "max_infographics_per_report": 0,
                "include_infographics": False,
            }
            # Auto-infer output format from uploaded source file type
            import os
            _docs = output_spec.get("documents") if isinstance(output_spec.get("documents"), dict) else {}
            _parsed = [dict(x) for x in list(_docs.get("parsed_documents") or []) if isinstance(x, dict)]
            for _pd in _parsed[:1]:
                _fn = str(_pd.get("filename") or "").strip().lower()
                _ext = os.path.splitext(_fn)[1]
                if _ext in {".docx", ".doc"}:
                    output_spec.setdefault("formats", [])
                    if "docx" not in output_spec["formats"]:
                        output_spec["formats"].append("docx")
                elif _ext in {".xlsx", ".xlsm", ".xls"}:
                    output_spec.setdefault("formats", [])
                    if "xlsx" not in output_spec["formats"]:
                        output_spec["formats"].append("xlsx")
                elif _ext == ".pdf":
                    output_spec.setdefault("formats", [])
                    if "pdf" not in output_spec["formats"]:
                        output_spec["formats"].append("pdf")
            if isinstance(context.output_spec, dict):
                context.output_spec["formats"] = list(output_spec.get("formats") or [])
        if delivery_mode == "agreement_clauses":
            strategy["mode"] = delivery_mode
            strategy["skip_toc"] = True
            strategy["skip_visuals"] = True
            strategy["numbering_style"] = str(delivery_compose.get("numbering_style") or "clause")
            strategy["section_count"] = int(delivery_compose.get("section_count") or strategy.get("section_count") or 8)
            strategy["outline_depth"] = int(delivery_compose.get("outline_depth") or 1)
            # Disable visuals for agreements
            strategy["visual_policy"] = {
                "min_visuals_per_report": 0,
                "max_visuals_per_report": 0,
                "min_infographics_per_report": 0,
                "max_infographics_per_report": 0,
                "include_infographics": False,
            }
        payload["compose_strategy"] = strategy
        logging.warning(
            "[writer_engine] agreement_detect | delivery_mode=%s strategy_mode=%s skip_toc=%s skip_visuals=%s numbering=%s gc_type=%s tc_mode=%s",
            delivery_mode,
            strategy.get("mode", ""),
            strategy.get("skip_toc", ""),
            strategy.get("skip_visuals", ""),
            strategy.get("numbering_style", ""),
            (output_spec.get("goal_contract") or {}).get("deliverable_type", ""),
            (output_spec.get("task_contract") or {}).get("deliverable_mode", ""),
        )

        preset = output_spec.get("profile_preset") if isinstance(output_spec.get("profile_preset"), dict) else {}
        compose_policy = preset.get("compose_policy") if isinstance(preset.get("compose_policy"), dict) else {}
        gp = dict(resolve_compose_policy(output_spec) or {})
        gp.update({k: v for k, v in compose_policy.items() if v is not None})
        output_spec["generation_policy"] = gp

        try:
            log_print(
                "[writer_engine] mode=%s preset=%s source=%s section_count=%s required_blocks=%s score=%s reasons=%s"
                % (
                    str(strategy.get("mode") or ""),
                    str(preset.get("preset_id") or ""),
                    str(preset.get("source") or ""),
                    int(strategy.get("section_count") or 0),
                    json.dumps(list(output_spec.get("required_blocks") or []), ensure_ascii=False),
                    int(route.get("score") or 0),
                    json.dumps(list(route.get("reasons") or []), ensure_ascii=False),
                ),
                flush=True,
            )
        except Exception:
            pass
        try:
            assembly = compose_policy.get("assembly_profile") if isinstance(compose_policy.get("assembly_profile"), dict) else {}
            log_print(
                "[writer_engine] assembly source=%s length=%s scan=%s visuals=%s hook=%s tags=%s signals=%s"
                % (
                    str(assembly.get("source") or ""),
                    str(assembly.get("length_band") or ""),
                    str(assembly.get("scannability") or ""),
                    str(assembly.get("visual_density") or ""),
                    str(assembly.get("hook_strength") or ""),
                    str(assembly.get("tagging_mode") or ""),
                    ",".join([str(x) for x in list(assembly.get("signals") or [])[:8]]),
                ),
                flush=True,
            )
        except Exception:
            pass
        try:
            compose_profile = dict(output_spec.get("compose_profile") or {})
            profile_preset = dict(output_spec.get("profile_preset") or {})
            prompt_contract = dict(output_spec.get("prompt_contract") or {})
            strategy_view = dict(strategy or {})

            preset_summary = {
                "preset_id": profile_preset.get("preset_id"),
                "source": profile_preset.get("source"),
                "publish_channel": (profile_preset.get("compose_policy") or {}).get("publish_channel"),
                "content_form": (profile_preset.get("compose_policy") or {}).get("content_form"),
                "required_blocks": (profile_preset.get("structure_contract") or {}).get("required_blocks"),
                "section_count": (profile_preset.get("structure_contract") or {}).get("section_count"),
                "citation_required": (profile_preset.get("evidence_policy") or {}).get("citation_required"),
                "deliverable": (profile_preset.get("output_contract") or {}).get("deliverable"),
            }
            prompt_summary = {
                "keys": sorted(list(prompt_contract.keys())),
                "must_include_count": len(list(prompt_contract.get("must_include") or [])),
                "forbidden_count": len(list(prompt_contract.get("forbidden_patterns") or [])),
                "has_identity": bool(str(prompt_contract.get("identity") or "").strip()),
                "has_style_ref_pos": bool(str((prompt_contract.get("style_reference") or {}).get("positive") or "").strip()),
                "style_markdown_len": len(str(prompt_contract.get("style_markdown") or "")),
                "style_markdown_compact_len": len(str(prompt_contract.get("style_markdown_compact") or "")),
            }
            strategy_summary = {
                "section_count": strategy_view.get("section_count"),
                "outline_depth": strategy_view.get("outline_depth"),
                "word_budget": strategy_view.get("word_budget"),
                "visual_policy": strategy_view.get("visual_policy"),
                "required_blocks": (strategy_view.get("structure_contract") or {}).get("required_blocks"),
                "deliverable": (strategy_view.get("output_contract") or {}).get("deliverable"),
            }

            log_print(
                "[writer_engine] compose profile | intent=%s audience=%s confidence=%s"
                % (
                    str(compose_profile.get("intent_statement") or "")[:120],
                    str(compose_profile.get("audience_model") or "")[:120],
                    str(compose_profile.get("confidence") or ""),
                ),
                flush=True,
            )
            log_print(
                "[writer_engine] preset summary | id=%s source=%s channel=%s form=%s sections=%s deliverable=%s citations=%s"
                % (
                    str(preset_summary.get("preset_id") or ""),
                    str(preset_summary.get("source") or ""),
                    str(preset_summary.get("publish_channel") or ""),
                    str(preset_summary.get("content_form") or ""),
                    int(preset_summary.get("section_count") or 0),
                    str(preset_summary.get("deliverable") or ""),
                    str(bool(preset_summary.get("citation_required"))),
                ),
                flush=True,
            )
            log_print(
                "[writer_engine] prompt contract | keys=%s must_include=%s forbidden=%s has_identity=%s has_style_ref=%s"
                % (
                    len(list(prompt_summary.get("keys") or [])),
                    int(prompt_summary.get("must_include_count") or 0),
                    int(prompt_summary.get("forbidden_count") or 0),
                    str(bool(prompt_summary.get("has_identity"))),
                    str(bool(prompt_summary.get("has_style_ref_pos"))),
                ),
                flush=True,
            )
            log_print(
                "[writer_engine] strategy summary | sections=%s depth=%s target_words=%s required_blocks=%s deliverable=%s"
                % (
                    int(strategy_summary.get("section_count") or 0),
                    int(strategy_summary.get("outline_depth") or 0),
                    int(((strategy_summary.get("word_budget") or {}).get("total_target") or 0)),
                    len(list(strategy_summary.get("required_blocks") or [])),
                    str(strategy_summary.get("deliverable") or ""),
                ),
                flush=True,
            )
        except Exception:
            pass

        tool_observations = list(payload.get("tool_observations") or [])
        tool_observations = self._build_document_tool_observations(
            output_spec=output_spec,
            base_observations=tool_observations,
        )
        if isinstance(context.output_spec, dict):
            context.output_spec["tool_observations"] = list(tool_observations or [])

        has_generated_visuals = self._has_planned_generated_visuals(strategy=strategy, output_spec=output_spec)
        if not has_generated_visuals and str(strategy.get("mode") or "").strip().lower() not in {"translation", "agreement_clauses"}:
            strategy["skip_visuals"] = True
            strategy["visual_policy"] = {
                "min_visuals_per_report": 0,
                "max_visuals_per_report": 0,
                "min_infographics_per_report": 0,
                "max_infographics_per_report": 0,
                "include_infographics": False,
            }
        subject_context = self._build_subject_context(output_spec)
        node_meta_for_subject = (
            output_spec.get("current_task_node_meta")
            if isinstance(output_spec.get("current_task_node_meta"), dict)
            else {}
        )
        subject_source_contract = (
            node_meta_for_subject.get("subject_source")
            if isinstance(node_meta_for_subject.get("subject_source"), dict)
            else None
        )
        upstream_artifacts_for_subject: Dict[str, Any] = {}
        if isinstance(output_spec.get("input_artifacts"), dict):
            upstream_artifacts_for_subject.update(dict(output_spec.get("input_artifacts") or {}))
        predecessor_for_subject = (
            output_spec.get("predecessor_artifacts")
            if isinstance(output_spec.get("predecessor_artifacts"), dict)
            else {}
        )
        for _pred_node_id, _pred_artifact in predecessor_for_subject.items():
            if not isinstance(_pred_artifact, dict):
                continue
            for _k, _v in _pred_artifact.items():
                if str(_k).startswith("_"):
                    continue
                upstream_artifacts_for_subject.setdefault(str(_k), _v)
        subject_resolution = await self._subject_resolver.resolve(
            user_query=raw_user_query,
            tool_observations=tool_observations,
            document_context=subject_context,
            subject_source=subject_source_contract,
            upstream_artifacts=upstream_artifacts_for_subject or None,
        )
        output_spec["subject_resolution"] = subject_resolution.model_dump()
        body_user_goal = self._build_body_user_goal(output_spec, raw_user_query)
        # Append cross-node data-flow context so the compose LLM sees the
        # same three layers every browser node sees: user's original ask,
        # the actual key-values upstream left behind, and (if compose is a
        # middle-of-graph node) what downstream consumers expect. When
        # upstream values are empty/placeholder, this block tells the LLM
        # honestly so it doesn't generate boilerplate on top of nothing.
        body_user_goal = self._augment_body_goal_with_data_flow(
            body_user_goal=body_user_goal,
            raw_user_query=raw_user_query,
            upstream_artifacts=upstream_artifacts_for_subject,
            node_meta=node_meta_for_subject,
        )
        language = "zh" if re.search(r"[\u4e00-\u9fff]", raw_user_query or body_user_goal or "") else "en"
        title_hint = self._build_title_hint(
            output_spec=output_spec,
            canonical_subject=str(subject_resolution.canonical_subject or ""),
            language=language,
            user_query=raw_user_query,
        )
        if title_hint:
            strategy["title_hint"] = title_hint
            # Surface title_hint via the shared nested profile_preset.metadata
            # dict. The subagent runtime shallow-copies output_spec for each
            # node, so a top-level mutation (e.g. output_spec["title_hint"])
            # does NOT reach the export node that triggers docx render. But
            # nested dicts (profile_preset, its metadata) are still shared
            # references — mutating them propagates to all subagents and back
            # to the parent's output_spec. This is the channel by which the
            # docx renderer (running in N_S_EXPORT) gets the LLM-derived
            # title that the writer (running in N_S1) just computed.
            preset_for_title = output_spec.get("profile_preset") if isinstance(output_spec.get("profile_preset"), dict) else None
            if isinstance(preset_for_title, dict):
                meta = preset_for_title.get("metadata")
                if not isinstance(meta, dict):
                    meta = {}
                    preset_for_title["metadata"] = meta
                meta["title_hint"] = title_hint
            try:
                log_print(
                    "[writer_engine] title hint selected | title=%s explicit=%s"
                    % (
                        json.dumps(title_hint, ensure_ascii=False),
                        bool(str((output_spec or {}).get("explicit_title_block") or "").strip()),
                    ),
                    flush=True,
                )
            except Exception:
                pass
        try:
            log_print(
                "[writer_engine] subject resolution | status=%s canonical=%s candidates=%s rationale=%s"
                % (
                    str(subject_resolution.status or ""),
                    str(subject_resolution.canonical_subject or "")[:120],
                    len(list(subject_resolution.candidate_subjects or [])),
                    str(subject_resolution.rationale or "")[:160],
                ),
                flush=True,
            )
        except Exception:
            pass
        selected_style_markdowns = payload.get("selected_style_markdowns") or []
        style_resolution = resolve_writer_style_prompt(
            output_spec=output_spec,
            payload=payload,
            selected_style_markdowns=selected_style_markdowns,
        )
        style_mode = str(style_resolution.get("mode") or "legacy").strip()
        style_parts = [
            self._sanitize_body_style_markdown(str(x or "").strip())
            for x in list(style_resolution.get("parts") or [])
            if str(x or "").strip()
        ]
        style_parts = [item for item in style_parts if item]
        selected_style_md = "\n\n".join(style_parts)
        if style_mode != "contract":
            selected_style_md = selected_style_md[:12000]
        try:
            log_print(
                "[writer_engine] style prompt | mode=%s selected_style_parts=%s merged_style_len=%s preview=%s"
                % (
                    style_mode,
                    len(style_parts),
                    len(selected_style_md),
                    json.dumps(selected_style_md[:160], ensure_ascii=False),
                ),
                flush=True,
            )
        except Exception:
            pass
        evidence_bundle = payload.get("evidence_bundle") if isinstance(payload.get("evidence_bundle"), dict) else {}
        evidence_bundle = normalize_evidence_bundle(evidence_bundle)
        evidence_bundle = self._build_document_evidence_bundle(output_spec=output_spec, base_bundle=evidence_bundle)
        evidence_bundle = self._build_multimodal_evidence_bundle(output_spec=output_spec, base_bundle=evidence_bundle)
        evidence_bundle = self._build_graph_artifact_evidence_bundle(output_spec=output_spec, base_bundle=evidence_bundle)
        evidence_bundle = normalize_evidence_bundle(evidence_bundle)
        # Agreement mode: inject uploaded document as full template/draft so the
        # outline planner and section writer can use it as the baseline structure.
        _strategy_mode = str(strategy.get("mode") or "").strip().lower()
        if _strategy_mode == "agreement_clauses":
            evidence_bundle = self._inject_agreement_template(output_spec=output_spec, bundle=evidence_bundle)
        elif _strategy_mode == "translation":
            evidence_bundle = self._inject_translation_source(output_spec=output_spec, bundle=evidence_bundle)
        task_ir_context = output_spec.get("task_ir") if isinstance(output_spec.get("task_ir"), dict) else {}
        content_task_context = output_spec.get("content_task_spec") if isinstance(output_spec.get("content_task_spec"), dict) else {}
        evidence_bundle = await enrich_evidence_with_user_request_facts(
            llm=getattr(self._pipeline, "_llm", None),
            evidence_bundle=evidence_bundle,
            user_request=raw_user_query,
            task_context={
                "task_ir_constraints": task_ir_context.get("constraints") if isinstance(task_ir_context, dict) else {},
                "content_task_spec": {
                    key: content_task_context.get(key)
                    for key in ("constraints", "schema", "research_requirements")
                    if key in content_task_context
                },
            },
        )
        evidence_bundle = normalize_evidence_bundle(evidence_bundle)
        payload["evidence_bundle"] = dict(evidence_bundle or {})
        if isinstance(context.output_spec, dict):
            context.output_spec["evidence_bundle"] = dict(evidence_bundle or {})
        writer_evidence_packet = WriterEvidencePacketBuilder().build(
            evidence_bundle=evidence_bundle,
            tool_observations=tool_observations,
            output_spec=output_spec,
            user_query=raw_user_query,
        )
        packet_runtime = persist_writer_evidence_packet(
            packet=writer_evidence_packet,
            evidence_bundle=evidence_bundle,
            tool_observations=tool_observations,
            mode="active_packet_replaces_projection_and_raw",
        )
        output_spec["writer_evidence_packet_runtime"] = dict(packet_runtime or {})
        if isinstance(context.output_spec, dict):
            context.output_spec["writer_evidence_packet_runtime"] = dict(packet_runtime or {})
        try:
            log_print(
                "[writer_engine] evidence inputs | tool_observations=%s evidence_results=%s confirmed_facts=%s user_request_facts=%s"
                % (
                    len([x for x in list(tool_observations or []) if isinstance(x, dict)]),
                    len([x for x in list((evidence_bundle or {}).get("results") or []) if isinstance(x, dict)]),
                    len([x for x in list((evidence_bundle or {}).get("confirmed_facts") or []) if str(x or "").strip()]),
                    len([x for x in list((evidence_bundle or {}).get("user_request_facts") or []) if isinstance(x, dict)]),
                ),
                flush=True,
            )
            graph_count = int((evidence_bundle or {}).get("graph_artifact_evidence_count") or 0)
            if graph_count:
                log_print(
                    "[writer_engine] graph artifact evidence | count=%d"
                    % graph_count,
                    flush=True,
                )
        except Exception:
            pass

        strict_blocker = self._resolve_strict_grounding_blocker(
            output_spec=output_spec,
            user_query=raw_user_query,
            tool_observations=tool_observations,
            evidence_bundle=evidence_bundle,
        )
        if strict_blocker:
            try:
                log_print("[writer_engine] strict grounding blocked generation | evidence=0", flush=True)
            except Exception:
                pass
            yield {"type": "answer", "content": strict_blocker + "\n\n"}
            return

        # Extract channel and audience for context-aware subject resolution
        preset_summary = output_spec.get("preset_summary") if isinstance(output_spec.get("preset_summary"), dict) else {}
        compose_profile = output_spec.get("compose_profile") if isinstance(output_spec.get("compose_profile"), dict) else {}
        channel = str(preset_summary.get("publish_channel") or "")
        audience = str(compose_profile.get("audience_model") or "")

        # Read execution_kind and schema.category out of content_task_spec
        # so the gate can short-circuit for browser / code / file tasks.
        _cts = output_spec.get("content_task_spec") if isinstance(output_spec.get("content_task_spec"), dict) else {}
        _ek = str((_cts or {}).get("execution_kind") or "").strip().lower()
        _schema = (_cts or {}).get("schema") if isinstance((_cts or {}).get("schema"), dict) else {}
        _sc = str((_schema or {}).get("category") or "").strip().lower()
        if _strategy_mode == "translation" and not _ek:
            _ek = "file"
        subject_gate = self._resolve_subject_generation_gate(
            user_query=raw_user_query,
            subject_resolution=output_spec.get("subject_resolution") or {},
            tool_observations=tool_observations,
            evidence_bundle=evidence_bundle,
            channel=channel,
            audience=audience,
            execution_kind=_ek,
            schema_category=_sc,
        )
        output_spec["subject_resolution_gate"] = dict(subject_gate or {})
        if isinstance(context.output_spec, dict):
            context.output_spec["subject_resolution_gate"] = dict(subject_gate or {})
        gate_action = str(subject_gate.get("action") or "proceed").strip().lower()
        if gate_action == "clarify":
            try:
                log_print(
                    "[writer_engine] subject gate | action=clarify evidence_strength=%s"
                    % int(subject_gate.get("evidence_strength") or 0),
                    flush=True,
                )
            except Exception:
                pass
            message = str(subject_gate.get("message") or "").strip()
            if message:
                yield {"type": "answer", "content": message + "\n\n"}
                return
        if gate_action == "disambiguate":
            body_user_goal = str(subject_gate.get("body_user_goal") or body_user_goal).strip() or body_user_goal
            output_spec["subject_resolution_gate_mode"] = "disambiguation"
            if isinstance(context.output_spec, dict):
                context.output_spec["subject_resolution_gate_mode"] = "disambiguation"
            try:
                log_print(
                    "[writer_engine] subject gate | action=disambiguate evidence_strength=%s"
                    % int(subject_gate.get("evidence_strength") or 0),
                    flush=True,
                )
            except Exception:
                pass
        compose_user_id = str(output_spec.get("user_id") or "anonymous")

        mode = str(strategy.get("mode") or "")
        output_spec["deferred_visuals_disabled"] = bool(strategy.get("skip_visuals"))
        if isinstance(context.output_spec, dict):
            context.output_spec["deferred_visuals_disabled"] = bool(strategy.get("skip_visuals"))
        # Record which writer path actually ran. The downstream document-level
        # retry gate reads this — sectional paths (where per-section eval+regen
        # already runs inside the writer loop) should NOT re-trigger a full
        # document retry; doc-level retry only makes sense for single-shot
        # The direct path has no inline section repair mechanism.
        # no inline repair mechanism.
        output_spec["__writer_path"] = (
            "sectional" if mode == "sectional_compose"
            else ("translation" if mode == "translation" else "single_shot")
        )
        if isinstance(context.output_spec, dict):
            context.output_spec["__writer_path"] = str(output_spec["__writer_path"])
        if mode == "translation":
            stream = self._pipeline.generate_translation(
                user_query=raw_user_query or body_user_goal,
                language=language,
                evidence_bundle=evidence_bundle,
                user_id=compose_user_id,
            )
        elif mode == "direct_compose":
            stream = self._pipeline.generate_direct(
                user_query=body_user_goal,
                language=language,
                strategy=strategy,
                tool_observations=tool_observations,
                selected_style_md=selected_style_md,
                evidence_bundle=evidence_bundle,
                writer_evidence_packet=writer_evidence_packet.model_dump(),
                user_id=compose_user_id,
            )
        else:
            stream = self._pipeline.generate(
                user_query=body_user_goal,
                language=language,
                strategy=strategy,
                tool_observations=tool_observations,
                selected_style_md=selected_style_md,
                evidence_bundle=evidence_bundle,
                writer_evidence_packet=writer_evidence_packet.model_dump(),
                user_id=compose_user_id,
            )
        buffered_answer_parts: List[str] = []
        async for evt in stream:
            if isinstance(evt, dict) and str(evt.get("type") or "") == "answer":
                buffered_answer_parts.append(self._strip_outer_markdown_fence(str(evt.get("content") or "")))
                continue
            if isinstance(evt, dict) and str(evt.get("type") or "") == "activity":
                # V3 work visibility comes from the graph node operation. Do
                # not translate writer-engine timeline prose into V3 items.
                if bool(payload.get("preserve_activity_events")):
                    yield evt
                continue
            yield evt

        final_content = "\n\n".join([part.strip() for part in buffered_answer_parts if str(part or "").strip()]).strip()
        # Translation mode: bypass all post-processing (fact grounding, image planning, etc.)
        # The translated content must be preserved exactly as produced by the translator.
        if mode == "translation":
            if final_content:
                yield {"type": "answer", "content": final_content + "\n\n"}
            return
        multimodal = output_spec.get("multimodal") if isinstance(output_spec.get("multimodal"), dict) else {}
        uploaded_assets = self._collect_uploaded_assets_for_compose(output_spec)
        existing_layout_hints = [dict(x) for x in list(multimodal.get("image_layout_hints") or []) if isinstance(x, dict)]
        compose_policy = strategy.get("compose_policy") if isinstance(strategy.get("compose_policy"), dict) else {}
        visual_preferences = (
            compose_policy.get("visual_preferences")
            if isinstance(compose_policy.get("visual_preferences"), dict)
            else {}
        )
        uploaded_image_insert_mode = str(
            visual_preferences.get("uploaded_image_insert_mode") or "auto"
        ).strip().lower()
        if uploaded_image_insert_mode not in {"auto", "reference_only", "preserve"}:
            uploaded_image_insert_mode = "auto"
        if final_content and uploaded_assets and uploaded_image_insert_mode != "reference_only":
            log_print(
                "[tool_writer_engine_compose][image_assets] "
                f"uploaded_assets={len(uploaded_assets)} existing_hints={len(existing_layout_hints)} "
                f"insert_mode={uploaded_image_insert_mode}",
                flush=True,
            )
            planner_result = await get_image_planner_service().plan_document_images(
                markdown=final_content,
                user_goal=body_user_goal,
                uploaded_assets=uploaded_assets,
            )
            layout_hints = merge_image_layout_hints(
                existing_layout_hints,
                list(planner_result.get("layout_hints") or []),
            )
            if layout_hints:
                final_content = await inject_images_inline(markdown=final_content, image_layout_hints=layout_hints)
                final_content = normalize_image_markdown(final_content)
                log_print(
                    "[tool_writer_engine_compose][image_insert] "
                    f"layout_hints={len(layout_hints)} markdown_images={final_content.count('![')}",
                    flush=True,
                )
        elif final_content and uploaded_assets:
            log_print(
                "[tool_writer_engine_compose][image_assets_skip] "
                f"uploaded_assets={len(uploaded_assets)} insert_mode={uploaded_image_insert_mode}",
                flush=True,
            )
        if final_content:
            yield {"type": "answer", "content": final_content + "\n\n"}
