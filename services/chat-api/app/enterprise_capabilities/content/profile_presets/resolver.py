from __future__ import annotations
from app.infrastructure.observability.config import log_print

import json
from typing import Any, Dict, List

from app.llm.types import Message, Role
from pydantic import BaseModel, Field

from app.llm.factory import get_request_scoped_llm_client
from app.enterprise_capabilities.content.profile_presets.catalog import PresetCatalog
from app.enterprise_capabilities.content.profile_presets.conflict_checker import PresetConflictChecker
from app.enterprise_capabilities.content.profile_presets.contracts import ComposeProfile, PresetCandidate, PresetResolution, ProfilePreset
from app.enterprise_capabilities.content.profile_presets.context_compaction import compact_output_spec_for_profile
from app.enterprise_capabilities.content.profile_presets.minimal_spec import normalize_minimal_spec
from app.enterprise_capabilities.content.profile_presets.quality_validator import PresetQualityValidator
from app.enterprise_capabilities.content.profile_presets.scorer import PresetScorer
from app.enterprise_capabilities.content.profile_presets.synthesizer import DynamicPresetSynthesizer
from app.enterprise_capabilities.data.script_engine.message_ops import last_user_text_from_dict_messages


class _ProfileExtract(BaseModel):
    intent_statement: str = ""
    deliverable_signature: str = ""
    audience_model: str = ""
    style_axes: Dict[str, Any] = Field(default_factory=dict)
    hard_constraints: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0


class _RankExtract(BaseModel):
    fit_score: float = 0.0
    constraint_score: float = 0.0
    reason: str = ""


class ProfilePresetResolver:
    def __init__(self) -> None:
        self._llm = get_request_scoped_llm_client(streaming=False, stage="planning")
        self._catalog = PresetCatalog()
        self._conflicts = PresetConflictChecker()
        self._scorer = PresetScorer()
        self._synth = DynamicPresetSynthesizer()
        self._quality = PresetQualityValidator()

    async def extract_compose_profile(self, *, messages: List[Dict[str, Any]], output_spec: Dict[str, Any], task_ir: Dict[str, Any]) -> ComposeProfile:
        user_text = last_user_text_from_dict_messages(messages)
        compact_messages: List[Dict[str, Any]] = []
        for msg in list(messages or [])[-8:]:
            if not isinstance(msg, dict):
                continue
            compact_messages.append(
                {
                    "role": str(msg.get("role") or ""),
                    "content": str(msg.get("content") or "")[:2000],
                }
            )
        payload = {
            "messages": compact_messages,
            "output_spec": compact_output_spec_for_profile(output_spec),
            "planning_evidence": dict(output_spec.get("planning_evidence") or {}) if isinstance(output_spec.get("planning_evidence"), dict) else {},
            "task_ir": task_ir,
        }
        system = (
            "Extract an open-world compose profile from the user request. "
            "Do not force predefined categories. "
            "If planning_evidence is present, use it as the source of truth for subject disambiguation, audience, domain context, and factual boundaries. "
            "Do not infer unsupported industries or acronym meanings from model priors. "
            "Return strict JSON only."
        )
        try:
            model = self._llm.with_structured_output(_ProfileExtract, method="function_calling")
            res = await model.ainvoke([Message(role=Role.SYSTEM, content=system), Message(role=Role.USER, content=json.dumps(payload, ensure_ascii=False, default=str))])
            if isinstance(res, _ProfileExtract):
                return ComposeProfile(
                    intent_statement=str(res.intent_statement or "").strip(),
                    deliverable_signature=str(res.deliverable_signature or "").strip(),
                    audience_model=str(res.audience_model or "").strip(),
                    style_axes=dict(res.style_axes or {}),
                    hard_constraints=dict(res.hard_constraints or {}),
                    raw_request=user_text,
                    confidence=float(res.confidence or 0.0),
                )
        except Exception:
            pass
        return ComposeProfile(intent_statement=user_text[:300], raw_request=user_text)

    async def _rank(self, *, compose_profile: ComposeProfile, preset: ProfilePreset) -> _RankExtract:
        system = (
            "You are a preset fitness scorer. Score how well a preset matches compose_profile. "
            "Return strict JSON: fit_score, constraint_score, reason in [0,1]."
        )
        payload = {"compose_profile": compose_profile.model_dump(), "preset": preset.model_dump()}
        try:
            model = self._llm.with_structured_output(_RankExtract, method="function_calling")
            res = await model.ainvoke([Message(role=Role.SYSTEM, content=system), Message(role=Role.USER, content=json.dumps(payload, ensure_ascii=False, default=str))])
            if isinstance(res, _RankExtract):
                return _RankExtract(
                    fit_score=max(0.0, min(1.0, float(res.fit_score or 0.0))),
                    constraint_score=max(0.0, min(1.0, float(res.constraint_score or 0.0))),
                    reason=str(res.reason or "").strip(),
                )
        except Exception:
            pass
        return _RankExtract(fit_score=0.55, constraint_score=0.55, reason="fallback")

    async def resolve(self, *, messages: List[Dict[str, Any]], output_spec: Dict[str, Any], task_ir: Dict[str, Any]) -> PresetResolution:
        profile = await self.extract_compose_profile(messages=messages, output_spec=output_spec, task_ir=task_ir)
        presets = self._catalog.list_candidates(output_spec=output_spec)

        ranked: List[PresetCandidate] = []
        # These candidates were already selected by the upstream workflow/style
        # resolver. Re-ranking every active skill here was a duplicate LLM
        # decision and could override an explicitly chosen writing contract.
        for p in presets:
            qv = self._quality.validate(compose_profile=profile, preset=p)
            c = self._scorer.score(
                preset=p,
                fit_score=1.0,
                constraint_score=float(qv.get("score") or 0.0),
                hard_conflicts=0 if bool(qv.get("ok")) else 1,
                soft_conflicts=0,
            )
            c.hard_conflicts = []
            if not bool(qv.get("ok")):
                c.hard_conflicts.append("preset_quality_below_threshold")
            c.soft_conflicts = []
            c.reason = "upstream_selected_writing_skill"
            p.metadata = dict(p.metadata or {})
            p.metadata["quality_validation"] = qv
            ranked.append(c)

        ranked.sort(key=lambda x: x.total_score, reverse=True)

        selected = None
        reason = ""
        filtered = [c for c in ranked if not c.hard_conflicts]
        user_filtered = [c for c in filtered if str(c.preset.source) == "user_db"]
        system_filtered = [c for c in filtered if str(c.preset.source) == "system_builtin"]
        other_filtered = [c for c in filtered if str(c.preset.source) not in {"user_db", "system_builtin"}]
        if user_filtered:
            selected = sorted(user_filtered, key=lambda x: x.total_score, reverse=True)[0].preset
            reason = "selected_user_db_priority"
        elif system_filtered:
            selected = sorted(system_filtered, key=lambda x: x.total_score, reverse=True)[0].preset
            reason = "selected_system_builtin_priority"
        elif other_filtered:
            selected = sorted(other_filtered, key=lambda x: x.total_score, reverse=True)[0].preset
            reason = "selected_by_score"

        need_dynamic = selected is None
        used_dynamic = False
        dynamic_quality_trace: Dict[str, Any] = {}
        if need_dynamic:
            selected = await self._synth.synthesize(compose_profile=profile, output_spec=output_spec, task_ir=task_ir)
            used_dynamic = True
            reason = "dynamic_preset_generated"
            qv = self._quality.validate(compose_profile=profile, preset=selected)
            dynamic_quality_trace = {"attempt": 1, "quality": qv}
            repair_attempt = 0
            while (not bool(qv.get("ok"))) and repair_attempt < 2:
                repair_attempt += 1
                selected = await self._synth.repair(
                    compose_profile=profile,
                    output_spec=output_spec,
                    task_ir=task_ir,
                    current_preset=selected,
                    issues=list(qv.get("issues") or []),
                )
                qv = self._quality.validate(compose_profile=profile, preset=selected)
                dynamic_quality_trace[f"repair_{repair_attempt}"] = qv
            if not bool(qv.get("ok")):
                reason = "dynamic_preset_generated_with_minimal_contract_fallback"
            try:
                log_print(
                    "[profile_preset][dynamic_quality] preset=%s ok=%s score=%.3f issues=%s"
                    % (
                        str(selected.preset_id or ""),
                        bool(qv.get("ok")),
                        float(qv.get("score") or 0.0),
                        json.dumps(list(qv.get("issues") or []), ensure_ascii=False),
                    ),
                    flush=True,
                )
            except Exception:
                pass
        else:
            if selected is not None:
                selected = normalize_minimal_spec(
                    preset=selected,
                    compose_profile=profile,
                    output_spec=output_spec,
                    task_ir=task_ir,
                )
            try:
                log_print(
                    "[profile_preset][selected] source=%s reason=%s candidates=user_db:%s system_builtin:%s other:%s"
                    % (
                        str(selected.source if selected else ""),
                        str(reason or ""),
                        len(user_filtered),
                        len(system_filtered),
                        len(other_filtered),
                    ),
                    flush=True,
                )
            except Exception:
                pass
        if selected is not None and used_dynamic:
            selected = normalize_minimal_spec(
                preset=selected,
                compose_profile=profile,
                output_spec=output_spec,
                task_ir=task_ir,
            )

        trace = {
            "compose_profile": profile.model_dump(),
            "ranked": [
                {
                    "preset_id": c.preset.preset_id,
                    "source": c.preset.source,
                    "fit_score": c.fit_score,
                    "constraint_score": c.constraint_score,
                    "risk_penalty": c.risk_penalty,
                    "total_score": c.total_score,
                    "hard_conflicts": c.hard_conflicts,
                    "soft_conflicts": c.soft_conflicts,
                    "reason": c.reason,
                    "quality_validation": dict((c.preset.metadata or {}).get("quality_validation") or {}),
                }
                for c in ranked
            ],
            "selected_preset_id": str(selected.preset_id if selected else ""),
            "decision_reason": reason,
            "candidate_source": "upstream_selected_writing_skills" if presets else "dynamic_fallback",
            "used_dynamic": used_dynamic,
            "dynamic_quality": dynamic_quality_trace,
        }

        return PresetResolution(
            selected_preset=selected,
            candidates=ranked,
            need_dynamic=need_dynamic,
            decision_reason=reason,
            used_dynamic=used_dynamic,
            trace=trace,
        )
