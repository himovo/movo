from __future__ import annotations
from app.infrastructure.observability.config import log_print

from typing import Any, Dict, List

from app.enterprise_capabilities.content.execution_mode.channel_policy import ExecutionChannelPolicyResolver
from app.enterprise_capabilities.content.execution_mode.contracts import ExecutionModeDecision


class ExecutionModeResolver:
    def __init__(self) -> None:
        self._channel_policy = ExecutionChannelPolicyResolver()

    def resolve(
        self,
        *,
        compose_policy: Dict[str, Any],
        structure_contract: Dict[str, Any],
        quality_gates: Dict[str, Any],
        evidence_policy: Dict[str, Any],
        prompt_contract: Dict[str, Any],
        user_query: str,
    ) -> ExecutionModeDecision:
        explicit = self._normalize_requested_mode(str(compose_policy.get("write_mode") or ""))
        content_form = str(compose_policy.get("content_form") or "").strip().lower()
        target_words = self._target_words(quality_gates)
        assembly = compose_policy.get("assembly_profile") if isinstance(compose_policy.get("assembly_profile"), dict) else {}
        length_band = str(assembly.get("length_band") or "").strip().lower()
        semantic_profile = self._semantic_profile(compose_policy)
        required_blocks = [str(x).strip() for x in list(structure_contract.get("required_blocks") or []) if str(x).strip()]
        strong_structure = len(required_blocks) >= 4
        source_dependency = str(semantic_profile.get("source_dependency") or "").strip().lower()
        operation_type = str(semantic_profile.get("operation_type") or "").strip().lower()
        global_consistency_need = str(semantic_profile.get("global_consistency_need") or "").strip().lower()
        source_grounded_rewrite = (
            source_dependency == "primary"
            and operation_type == "rewrite_transform"
            and global_consistency_need == "high"
        )
        explicit_demotions: List[str] = []
        document_scale_scope_large = self._should_keep_document_scale(
            content_form=content_form,
            target_words=target_words,
            length_band=length_band,
            semantic_profile=semantic_profile,
            required_blocks=required_blocks,
        )

        if explicit == "document_scale_compose" and not document_scale_scope_large:
            explicit = "auto"
            explicit_demotions.append("explicit_document_scale_requires_large_scope")

        if explicit == "sectional_compose" and self._should_demote_explicit_sectional(
            content_form=content_form,
            target_words=target_words,
            length_band=length_band,
            semantic_profile=semantic_profile,
        ):
            explicit = "auto"
            explicit_demotions.append("explicit_sectional_requires_long_word_budget")

        # Inferred write_mode from semantic policy is advisory for publishable articles.
        # Default to single-pass unless the task is clearly document-scale or direct is disallowed.
        if explicit in {"sectional_compose", "compact_block_compose"} and (
            (source_grounded_rewrite and target_words <= 8000)
            or (not strong_structure and self._prefer_single_pass_default(
            content_form=content_form,
            target_words=target_words,
            length_band=length_band,
            semantic_profile=semantic_profile,
            ))
        ):
            explicit = "auto"

        if explicit != "auto":
            decision = ExecutionModeDecision(mode=explicit, score=-1, reasons=[f"explicit_write_mode={explicit}"])
            self._log_decision(decision)
            return decision

        channel_policy = self._channel_policy.resolve(compose_policy=compose_policy, quality_gates=quality_gates)
        allowed_modes = set(channel_policy.allowed_modes or [])
        reasons: List[str] = list(explicit_demotions) + list(channel_policy.reasons or [])

        semantic_document_scale = bool(semantic_profile.get("document_scale"))
        semantic_single_pass = bool(semantic_profile.get("single_pass_feasible", True))
        semantic_section_independence = str(semantic_profile.get("section_independence") or "").strip().lower()
        semantic_narrative_requirement = str(semantic_profile.get("narrative_requirement") or "").strip().lower()
        semantic_recommended = self._normalize_requested_mode(str(semantic_profile.get("recommended_execution_mode") or ""))
        if not semantic_narrative_requirement and str(semantic_profile.get("narrative_posture") or "").strip():
            semantic_narrative_requirement = "high"

        if source_grounded_rewrite and target_words <= 8000 and "direct_compose" in allowed_modes:
            reasons.append("source_grounded_rewrite_single_pass")
            decision = ExecutionModeDecision(mode="direct_compose", score=0, reasons=reasons)
            self._log_decision(decision)
            return decision

        # Evidence floor: document_scale_compose can over-expand a thin report.
        # When evidence is thin AND the word budget is
        # modest, refuse document_scale and let the lighter modes take over.
        evidence_hint = int(compose_policy.get("evidence_strength_hint") or 0)
        evidence_too_thin = (
            evidence_hint > 0
            and evidence_hint < 4
            and target_words < 1500
        )
        if semantic_document_scale and "document_scale_compose" in allowed_modes and not evidence_too_thin and document_scale_scope_large:
            reasons.append("semantic_document_scale")
            decision = ExecutionModeDecision(mode="document_scale_compose", score=1, reasons=reasons)
            self._log_decision(decision)
            return decision
        if semantic_document_scale and not document_scale_scope_large:
            reasons.append("semantic_document_scale_requires_large_scope")
        if evidence_too_thin:
            reasons.append(f"evidence_floor_blocked_document_scale evidence_hint={evidence_hint} target_words={target_words}")

        if semantic_single_pass and "direct_compose" in allowed_modes:
            reasons.append("semantic_single_pass_feasible")
            if semantic_narrative_requirement in {"medium", "high"}:
                reasons.append(f"semantic_narrative_requirement={semantic_narrative_requirement}")
            decision = ExecutionModeDecision(mode="direct_compose", score=0, reasons=reasons)
            self._log_decision(decision)
            return decision

        if (
            strong_structure
            and target_words > 8000
            and semantic_section_independence in {"medium", "high"}
            and "sectional_compose" in allowed_modes
        ):
            reasons.append("strong_required_structure_with_long_independent_sections")
            decision = ExecutionModeDecision(mode="sectional_compose", score=1, reasons=reasons)
            self._log_decision(decision)
            return decision

        if (
            not semantic_single_pass
            and (semantic_section_independence in {"medium", "high"} or not semantic_section_independence)
            and "sectional_compose" in allowed_modes
        ):
            reasons.append(
                f"semantic_section_independence={semantic_section_independence}" if semantic_section_independence else "semantic_single_pass_infeasible"
            )
            decision = ExecutionModeDecision(mode="sectional_compose", score=1, reasons=reasons)
            self._log_decision(decision)
            return decision

        if (
            semantic_recommended in allowed_modes
            and semantic_recommended != "auto"
            and not (semantic_recommended == "document_scale_compose" and not document_scale_scope_large)
        ):
            reasons.append(f"semantic_recommended={semantic_recommended}")
            decision = ExecutionModeDecision(mode=semantic_recommended, score=0, reasons=reasons)
            self._log_decision(decision)
            return decision

        if "direct_compose" in allowed_modes:
            reasons.append("default_single_pass")
            decision = ExecutionModeDecision(mode="direct_compose", score=0, reasons=reasons)
            self._log_decision(decision)
            return decision

        if max(target_words, 0) > 20000 and "document_scale_compose" in allowed_modes:
            reasons.append("word_budget>20000")
            decision = ExecutionModeDecision(mode="document_scale_compose", score=1, reasons=reasons)
            self._log_decision(decision)
            return decision

        if len(required_blocks) >= 10 and target_words > 8000 and "sectional_compose" in allowed_modes:
            reasons.append("required_blocks_extremely_high_with_long_target")
            decision = ExecutionModeDecision(mode="sectional_compose", score=1, reasons=reasons)
            self._log_decision(decision)
            return decision

        if length_band == "long" and target_words > 8000 and "sectional_compose" in allowed_modes:
            reasons.append("long_form_fallback")
            decision = ExecutionModeDecision(mode="sectional_compose", score=1, reasons=reasons)
            self._log_decision(decision)
            return decision

        if "direct_compose" not in allowed_modes:
            fallback_mode = "document_scale_compose" if "document_scale_compose" in allowed_modes else (
                "sectional_compose" if "sectional_compose" in allowed_modes else "compact_block_compose"
            )
            reasons.append("fallback_to_allowed_mode")
            decision = ExecutionModeDecision(mode=fallback_mode, score=1, reasons=reasons)
            self._log_decision(decision)
            return decision

        decision = ExecutionModeDecision(mode="direct_compose", score=0, reasons=reasons)
        self._log_decision(decision)
        return decision

    def _normalize_requested_mode(self, raw: str) -> str:
        token = str(raw or "").strip().lower()
        mapping = {
            "": "auto",
            "auto": "auto",
            "direct": "direct_compose",
            "direct_compose": "direct_compose",
            "compact": "compact_block_compose",
            "compact_block": "compact_block_compose",
            "compact_block_compose": "compact_block_compose",
            "structured": "sectional_compose",
            "sectional": "sectional_compose",
            "sectional_compose": "sectional_compose",
            "document_scale": "document_scale_compose",
            "document_scale_compose": "document_scale_compose",
        }
        return mapping.get(token, "auto")

    def _target_words(self, quality_gates: Dict[str, Any]) -> int:
        target = int(quality_gates.get("target_words") or 0)
        min_words = int(quality_gates.get("min_words") or 0)
        max_words = int(quality_gates.get("max_words") or 0)
        if target > 0:
            return target
        if min_words > 0 and max_words >= min_words:
            return (min_words + max_words) // 2
        return max_words or min_words or 0

    def _prefer_single_pass_default(
        self,
        *,
        content_form: str,
        target_words: int,
        length_band: str,
        semantic_profile: Dict[str, Any],
    ) -> bool:
        if bool(semantic_profile.get("single_pass_feasible", False)):
            return True
        if bool(semantic_profile.get("document_scale", False)):
            return False
        publishable_forms = {
            "article",
            "blog_article",
            "wechat_article",
            "weibo_article",
            "xiaohongshu_article",
            "post",
            "public_post",
        }
        if content_form in publishable_forms and target_words <= 3000:
            return True
        if content_form in {"report", "whitepaper", "handbook"}:
            return False
        return length_band != "long" and target_words <= 3000

    def _should_demote_explicit_sectional(
        self,
        *,
        content_form: str,
        target_words: int,
        length_band: str,
        semantic_profile: Dict[str, Any],
    ) -> bool:
        if bool(semantic_profile.get("document_scale", False)):
            return False
        if content_form in {"whitepaper", "handbook"}:
            return False
        if length_band == "long" and target_words > 8000:
            return False
        return target_words <= 8000

    def _should_keep_document_scale(
        self,
        *,
        content_form: str,
        target_words: int,
        length_band: str,
        semantic_profile: Dict[str, Any],
        required_blocks: List[str],
    ) -> bool:
        if target_words >= 8000:
            return True
        if len(required_blocks) >= 6 and target_words >= 5000:
            return True
        if length_band == "long" and target_words >= 5000:
            return True
        if content_form in {"whitepaper", "handbook"}:
            return target_words <= 0 or target_words >= 4000

        section_independence = str(semantic_profile.get("section_independence") or "").strip().lower()
        consumption_mode = str(semantic_profile.get("audience_consumption_mode") or "").strip().lower()
        return (
            bool(semantic_profile.get("document_scale", False))
            and target_words >= 6000
            and (section_independence == "high" or consumption_mode == "reference_read")
        )

    def _semantic_profile(self, compose_policy: Dict[str, Any]) -> Dict[str, Any]:
        delivery = compose_policy.get("delivery_profile") if isinstance(compose_policy.get("delivery_profile"), dict) else {}
        profile = delivery.get("semantic_profile") if isinstance(delivery.get("semantic_profile"), dict) else {}
        return dict(profile or {})

    def _log_decision(self, decision: ExecutionModeDecision) -> None:
        try:
            log_print(
                "[execution_mode] mode=%s score=%s reasons=%s"
                % (
                    str(decision.mode or ""),
                    int(decision.score or 0),
                    ",".join([str(x) for x in list(decision.reasons or [])[:8]]),
                ),
                flush=True,
            )
        except Exception:
            pass
