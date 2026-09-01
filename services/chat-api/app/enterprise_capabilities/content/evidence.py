"""Evidence input boundary for ASKAI's governed long-form writer."""

from __future__ import annotations

from typing import Any

from app.enterprise_capabilities.evidence.foundation import normalize_evidence_bundle


def resolve_content_evidence(turn_context: dict[str, Any]) -> dict[str, Any]:
    """Consume the trusted upstream bundle; never ask the model to copy evidence."""

    bundle = turn_context.get("evidence_bundle")
    return normalize_evidence_bundle(bundle if isinstance(bundle, dict) else {})


__all__ = ["resolve_content_evidence"]
