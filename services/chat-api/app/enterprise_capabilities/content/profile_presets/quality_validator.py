from __future__ import annotations

from typing import Any, Dict, List

from app.enterprise_capabilities.content.profile_presets.contracts import ComposeProfile, ProfilePreset


class PresetQualityValidator:
    """Generic preset quality checks (no task-type hardcoding)."""

    def validate(self, *, compose_profile: ComposeProfile, preset: ProfilePreset) -> Dict[str, Any]:
        issues: List[str] = []
        warnings: List[str] = []

        compose = dict(preset.compose_policy or {})
        structure = dict(preset.structure_contract or {})
        output = dict(preset.output_contract or {})
        anti = dict(preset.anti_patterns or {})
        style_ref = dict(preset.style_reference or {})
        formatting = dict(preset.formatting_rules or {})
        must_include = [str(x).strip() for x in (preset.must_include or []) if str(x).strip()]

        score = 1.0

        if not str(preset.identity or "").strip():
            issues.append("missing_identity")
            score -= 0.18
        if not str(style_ref.get("positive") or "").strip():
            issues.append("missing_style_reference_positive")
            score -= 0.14
        if not str(style_ref.get("negative") or "").strip():
            warnings.append("missing_style_reference_negative")
            score -= 0.04
        required = [str(x).strip() for x in (structure.get("required_blocks") or []) if str(x).strip()]
        if len(required) < 3:
            issues.append("insufficient_required_blocks")
            score -= 0.16
        fw = [str(x).strip() for x in (anti.get("forbidden_words") or []) if str(x).strip()]
        if not fw:
            warnings.append("missing_forbidden_words")
            score -= 0.06
        if not formatting:
            warnings.append("missing_formatting_rules")
            score -= 0.05
        if not must_include:
            warnings.append("missing_must_include")
            score -= 0.05
        if "format" not in output:
            issues.append("missing_output_format")
            score -= 0.12

        # Generic anti-template signal: too little relation with user's profile.
        profile_signal = 0
        txt = (compose_profile.intent_statement + " " + compose_profile.deliverable_signature + " " + compose_profile.audience_model).strip()
        if txt:
            for token in [str(preset.identity or ""), str(compose.get("tone") or ""), str(compose.get("content_form") or "")]:
                if token and token in txt:
                    profile_signal += 1
        if profile_signal == 0:
            warnings.append("weak_profile_alignment_signal")
            score -= 0.08

        score = max(0.0, min(1.0, score))
        return {
            "ok": score >= 0.62 and len(issues) <= 1,
            "score": score,
            "issues": issues,
            "warnings": warnings,
        }
