"""Two-path routing policy for the DSH long-form content capability."""

from __future__ import annotations

from typing import Any

from app.enterprise_capabilities.content.execution_mode.resolver import ExecutionModeResolver


class ContentWriterRouter:
    """Collapse legacy writer modes to direct long-form or sectional ultra-long."""

    def __init__(self, resolver: ExecutionModeResolver | None = None) -> None:
        self._resolver = resolver or ExecutionModeResolver()

    def apply(self, *, output_spec: dict[str, Any], user_query: str) -> dict[str, Any]:
        preset = output_spec.get("profile_preset") if isinstance(output_spec.get("profile_preset"), dict) else {}
        compose = dict(preset.get("compose_policy") or {})
        structure = dict(preset.get("structure_contract") or {})
        quality = dict(preset.get("quality_gates") or {})
        decision = self._resolver.resolve(
            compose_policy=compose,
            structure_contract=structure,
            quality_gates=quality,
            evidence_policy=dict(preset.get("evidence_policy") or {}),
            prompt_contract=dict(preset.get("prompt_contract") or {}),
            user_query=user_query,
        )
        resolved = str(decision.mode or "direct_compose")
        mode = (
            "sectional_compose"
            if resolved in {"sectional_compose", "document_scale_compose"}
            else "direct_compose"
        )
        compose["write_mode"] = mode
        preset["compose_policy"] = compose
        output_spec["profile_preset"] = preset
        return {
            "mode": mode,
            "resolved_legacy_mode": resolved,
            "reasons": list(decision.reasons or []),
        }


__all__ = ["ContentWriterRouter"]
