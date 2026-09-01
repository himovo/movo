from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ExecutionChannelPolicy:
    allowed_modes: List[str] = field(default_factory=lambda: ["direct_compose", "compact_block_compose", "sectional_compose", "document_scale_compose"])
    preferred_mode: str = "direct_compose"
    reasons: List[str] = field(default_factory=list)


class ExecutionChannelPolicyResolver:
    def resolve(
        self,
        *,
        compose_policy: Dict[str, Any],
        quality_gates: Dict[str, Any],
    ) -> ExecutionChannelPolicy:
        content_form = str(compose_policy.get("content_form") or "").strip().lower() or "article"
        delivery_profile = compose_policy.get("delivery_profile") if isinstance(compose_policy.get("delivery_profile"), dict) else {}
        assembly = compose_policy.get("assembly_profile") if isinstance(compose_policy.get("assembly_profile"), dict) else {}
        length_band = str(assembly.get("length_band") or "").strip().lower()
        scannability = str(assembly.get("scannability") or "").strip().lower()
        consumption_mode = str(assembly.get("consumption_mode") or delivery_profile.get("consumption_mode") or "").strip().lower()
        target_words = self._target_words(quality_gates)

        reasons: List[str] = []
        long_form = (
            content_form in {"whitepaper", "handbook"}
            or target_words > 20000
            or (length_band == "long" and target_words > 8000)
        )

        if long_form:
            reasons.append("long_form_document_policy")
            return ExecutionChannelPolicy(
                allowed_modes=["sectional_compose", "document_scale_compose"],
                preferred_mode="document_scale_compose" if target_words > 20000 or content_form in {"whitepaper", "handbook"} else "sectional_compose",
                reasons=reasons,
            )

        compact_read = consumption_mode == "mobile_read"
        if not compact_read and content_form in {"article", "post", "public_post", "newsletter", "report", "brief", "memo"}:
            compact_read = scannability == "high" and (target_words <= 0 or target_words <= 1600)
        if compact_read:
            reasons.append("compact_readability_policy")
            return ExecutionChannelPolicy(
                allowed_modes=["direct_compose", "compact_block_compose"],
                preferred_mode="direct_compose",
                reasons=reasons,
            )

        reasons.append("generic_article_policy")
        return ExecutionChannelPolicy(
            allowed_modes=["direct_compose", "compact_block_compose", "sectional_compose"],
            preferred_mode="direct_compose",
            reasons=reasons,
        )

    @staticmethod
    def _target_words(quality_gates: Dict[str, Any]) -> int:
        target = int(quality_gates.get("target_words") or 0)
        min_words = int(quality_gates.get("min_words") or 0)
        max_words = int(quality_gates.get("max_words") or 0)
        if target > 0:
            return target
        if min_words > 0 and max_words >= min_words:
            return (min_words + max_words) // 2
        return max_words or min_words or 0
