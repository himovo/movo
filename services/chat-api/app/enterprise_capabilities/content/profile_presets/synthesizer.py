from __future__ import annotations
from app.infrastructure.observability.config import log_print

import json
from typing import Any, Dict, List

from app.llm.types import Message, Role

from app.llm.factory import get_request_scoped_llm_client
from app.enterprise_capabilities.content.profile_presets.contracts import ComposeProfile, ProfilePreset
from app.enterprise_capabilities.content.profile_presets.context_compaction import compact_output_spec_for_profile
from app.enterprise_capabilities.content.profile_presets.minimal_spec import normalize_minimal_spec
from app.enterprise_capabilities.content.profile_presets.prompt_constraints import VISUAL_BODY_SEPARATION_CONSTRAINT


class DynamicPresetSynthesizer:
    def __init__(self) -> None:
        self._llm = get_request_scoped_llm_client(streaming=False, stage="planning")

    def _normalize(self, *, preset: ProfilePreset, compose_profile: ComposeProfile, output_spec: Dict[str, Any], task_ir: Dict[str, Any], fallback_id: str) -> ProfilePreset:
        p = preset.model_copy(deep=True)
        p.source = "dynamic"
        if not str(p.preset_id or "").strip():
            p.preset_id = fallback_id
        return normalize_minimal_spec(
            preset=p,
            compose_profile=compose_profile,
            output_spec=output_spec,
            task_ir=task_ir,
        )

    async def synthesize(self, *, compose_profile: ComposeProfile, output_spec: Dict[str, Any], task_ir: Dict[str, Any]) -> ProfilePreset:
        payload = {
            "compose_profile": compose_profile.model_dump(),
            "task_ir": task_ir,
            "output_spec": compact_output_spec_for_profile(output_spec),
        }
        system = (
            "You are a profile preset synthesizer. Create a runnable writing preset from compose_profile. "
            "No fixed-form enum filling. Return strict JSON matching ProfilePreset fields. "
            "The preset must not conflict with compose_profile or output_spec. "
            "Mandatory non-empty fields: identity (single string), style_reference.positive, "
            "structure_contract.required_blocks, anti_patterns.forbidden_words, "
            "formatting_rules, quality_gates.min_words/max_words, output_contract.format. "
            "EXTREMELY IMPORTANT CONSTRAINTS:\n"
            "1. `quality_gates.min_words` and `quality_gates.max_words` MUST be positive INTEGERS chosen for the deliverable type. "
            "Inherit from compose_profile.min_words/max_words when present; otherwise infer reasonable values from the user's intent "
            "(e.g. resume / cover letter ~ 300-700; FAQ / manual ~ 600-1500; long article 1500-3000). "
            "Never return 0, never return a string, never omit these fields.\n"
            "2. If `output_spec.task_contract.evidence_mode` is 'optional' or omitted, you MUST set `evidence_policy.citation_required` to false.\n"
            "3. If `output_spec.required_blocks` exists, you MUST use them as the primary `structure_contract.required_blocks`. DO NOT add academic formats like '摘要' (Abstract) or '参考文献' (References) unless explicitly asked.\n"
            "4. `structure_contract.required_blocks` MUST be a JSON ARRAY of DISTINCT short strings (one section name per element). "
            "When `output_spec.required_blocks` exists, preserve that list exactly: do not add, remove, reorder, or pad sections. "
            "Example: [\"Header\", \"Summary\", \"Skills\", \"Experience\"]. "
            "DO NOT join the section names into one string with separators like ' + ', ' → ', ' | ' or commas — "
            "each element of the array is one section.\n"
            "5. `identity` MUST be a single flat string (e.g. 'AI-company resume writer for senior backend engineers'). "
            "Do NOT return identity as an object/dict; if you have multiple facets to capture, fold them into one sentence.\n"
            "6. `structure_contract.required_blocks` element language MUST match the user's writing language "
            "(infer from compose_profile.raw_request / intent_statement). When the user writes in Chinese, "
            "produce Chinese section names like ['个人信息','专业总结','工作经验','项目经历','技能','教育背景']; "
            "do NOT mix raw English tokens like 'header','summary','experience' into a Chinese deliverable.\n"
            "7. `structure_contract.required_blocks` ORDER is the reader-facing order. Put the most natural first "
            "section first (e.g. for a resume: header/个人信息 → summary/专业总结 → experience/工作经验 → "
            "projects/项目经历 → skills/技能 → education/教育背景). Downstream WILL preserve this order verbatim, "
            "so do not rely on later code to reorder.\n"
            "8. For short-form deliverables (resume / cover letter / email / JD / one-pager), set "
            "`structure_contract.numbering_style` to 'none' so section headings render without leading numbers. "
            "Use 'hierarchical' only for long reports / manuals where '1.', '2.' numbering is reader-helpful.\n"
            "9. " + VISUAL_BODY_SEPARATION_CONSTRAINT
        )
        # Plan A diagnostic logging: surface WHY the LLM call falls back so we
        # can tell apart (a) schema-too-open text-mode fragility,
        # (b) JSON parsing errors, (c) Pydantic validation errors,
        # (d) timeouts / API errors. Without this the bare except hid the
        # real reason for months.
        _signature = str(compose_profile.deliverable_signature or "").strip() or "(empty)"
        try:
            model = self._llm.with_structured_output(ProfilePreset, method="function_calling")
            res = await model.ainvoke(
                [
                    Message(role=Role.SYSTEM, content=system),
                    Message(role=Role.USER, content=json.dumps(payload, ensure_ascii=False, default=str)),
                ]
            )
            if isinstance(res, ProfilePreset):
                log_print(
                    f"[synthesizer] synthesize OK | signature={_signature} "
                    f"required_blocks={len(list((res.structure_contract or {}).get('required_blocks') or []))} "
                    f"min_words={(res.quality_gates or {}).get('min_words')} "
                    f"max_words={(res.quality_gates or {}).get('max_words')}",
                    flush=True,
                )
                return self._normalize(
                    preset=res,
                    compose_profile=compose_profile,
                    output_spec=output_spec,
                    task_ir=task_ir,
                    fallback_id="dynamic.preset.generated",
                )
            log_print(
                f"[synthesizer] synthesize unexpected return type | signature={_signature} "
                f"got={type(res).__name__}",
                flush=True,
            )
        except Exception as exc:
            import traceback as _tb
            _summary = str(exc).replace("\n", " | ")[:400]
            log_print(
                f"[synthesizer] synthesize FAILED → fallback | signature={_signature} "
                f"error_type={type(exc).__name__} error={_summary}",
                flush=True,
            )
            # Full traceback only at DEBUG so production stays quiet but we
            # have it on hand the moment we open the log.
            log_print(f"[synthesizer] traceback:\n{_tb.format_exc()}", flush=True)
        # Fallback that respects compose_profile when LLM synthesis fails.
        # Hard-coded 1200-2600 was the source of the "everything looks like
        # a long report" symptom — short-form deliverables (resume / cover
        # letter / email) ended up in document_scale_compose mode because of
        # this number alone. Fall back to compose_profile's hints first;
        # only use a generic mid-range when nothing else is known.
        _fb_min = 0
        _fb_max = 0
        try:
            _fb_min = int(getattr(compose_profile, "min_words", 0) or 0)
            _fb_max = int(getattr(compose_profile, "max_words", 0) or 0)
        except Exception:
            _fb_min, _fb_max = 0, 0
        if _fb_min <= 0 or _fb_max <= 0:
            # Conservative defaults that won't accidentally trigger
            # long-form document mode (>=1500 target_words).
            _fb_min, _fb_max = 600, 1200
        _fb_signature = str(getattr(compose_profile, "deliverable_signature", "") or "").strip()
        _fb_identity = (
            f"Preset for {_fb_signature}" if _fb_signature else "Generic dynamic content preset"
        )
        fallback = ProfilePreset(
            preset_id="dynamic.preset.fallback",
            source="dynamic",
            identity=_fb_identity,
            compose_policy={"tone": "professional", "content_form": "article"},
            structure_contract={"required_blocks": list((output_spec.get("required_blocks") or []))},
            evidence_policy={"citation_required": bool(((output_spec.get("task_contract") or {}).get("evidence_mode") == "required"))},
            quality_gates={"min_words": _fb_min, "max_words": _fb_max},
            output_contract={"format": "markdown", "deliverable": "article"},
        )
        return self._normalize(
            preset=fallback,
            compose_profile=compose_profile,
            output_spec=output_spec,
            task_ir=task_ir,
            fallback_id="dynamic.preset.fallback",
        )

    async def repair(
        self,
        *,
        compose_profile: ComposeProfile,
        output_spec: Dict[str, Any],
        task_ir: Dict[str, Any],
        current_preset: ProfilePreset,
        issues: List[str],
    ) -> ProfilePreset:
        payload = {
            "compose_profile": compose_profile.model_dump(),
            "task_ir": task_ir,
            "output_spec": compact_output_spec_for_profile(output_spec),
            "current_preset": current_preset.model_dump(),
            "quality_issues": [str(x) for x in (issues or []) if str(x).strip()],
        }
        system = (
            "Repair the profile preset by filling missing required fields while preserving user intent. "
            "Do not change meaning. Return strict ProfilePreset JSON. "
            "Mandatory non-empty: identity, style_reference.positive, "
            "structure_contract.required_blocks, anti_patterns.forbidden_words, "
            "formatting_rules, quality_gates.min_words/max_words, output_contract.format. "
            "EXTREMELY IMPORTANT CONSTRAINTS:\n"
            "1. You MUST inherit `min_words` and `max_words` directly from `compose_profile.min_words`/`max_words` safely, DO NOT inflate them.\n"
            "2. If `output_spec.task_contract.evidence_mode` is 'optional' or omitted, you MUST set `evidence_policy.citation_required` to false.\n"
            "3. If `output_spec.required_blocks` exists, you MUST preserve it exactly as `structure_contract.required_blocks`: do not add, remove, reorder, or pad sections. DO NOT add academic formats like '摘要' (Abstract) or '参考文献' (References) unless explicitly asked.\n"
            "4. " + VISUAL_BODY_SEPARATION_CONSTRAINT
        )
        # Plan A diagnostic logging on the repair pass too — same rationale
        # as synthesize() above.
        _repair_sig = str(compose_profile.deliverable_signature or "").strip() or "(empty)"
        try:
            model = self._llm.with_structured_output(ProfilePreset, method="function_calling")
            res = await model.ainvoke(
                [
                    Message(role=Role.SYSTEM, content=system),
                    Message(role=Role.USER, content=json.dumps(payload, ensure_ascii=False, default=str)),
                ]
            )
            if isinstance(res, ProfilePreset):
                log_print(
                    f"[synthesizer] repair OK | signature={_repair_sig} "
                    f"current_preset_id={current_preset.preset_id} "
                    f"issues={len(issues or [])}",
                    flush=True,
                )
                return self._normalize(
                    preset=res,
                    compose_profile=compose_profile,
                    output_spec=output_spec,
                    task_ir=task_ir,
                    fallback_id=str(current_preset.preset_id or "dynamic.preset.repaired"),
                )
            log_print(
                f"[synthesizer] repair unexpected return type | signature={_repair_sig} "
                f"got={type(res).__name__}",
                flush=True,
            )
        except Exception as exc:
            import traceback as _tb
            _summary = str(exc).replace("\n", " | ")[:400]
            log_print(
                f"[synthesizer] repair FAILED → keep current | signature={_repair_sig} "
                f"error_type={type(exc).__name__} error={_summary}",
                flush=True,
            )
            log_print(f"[synthesizer] traceback:\n{_tb.format_exc()}", flush=True)
        return self._normalize(
            preset=current_preset,
            compose_profile=compose_profile,
            output_spec=output_spec,
            task_ir=task_ir,
            fallback_id=str(current_preset.preset_id or "dynamic.preset.repaired"),
        )
