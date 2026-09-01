"""Bridge trusted execution evidence into the existing presentation engine."""

from __future__ import annotations

from typing import Any

from app.enterprise_capabilities.evidence.foundation import normalize_evidence_bundle


def presentation_tool_observations(turn_context: dict[str, Any]) -> list[dict[str, str]]:
    bundle = normalize_evidence_bundle(
        turn_context.get("evidence_bundle")
        if isinstance(turn_context.get("evidence_bundle"), dict)
        else {}
    )
    observations: list[dict[str, str]] = []
    for index, item in enumerate(list(bundle.get("results") or []), start=1):
        if not isinstance(item, dict):
            continue
        summary = str(item.get("content") or item.get("summary") or "").strip()
        if not summary:
            continue
        observations.append({
            "evidence_id": f"ev_{index}",
            "tool": str(item.get("tool") or "upstream_evidence")[:80],
            "summary": summary,
            "source_label": str(
                item.get("title") or item.get("source_url") or item.get("source") or f"source_{index}"
            )[:500],
        })
    if not observations:
        for index, fact in enumerate(list(bundle.get("confirmed_facts") or []), start=1):
            text = str(fact or "").strip()
            if text:
                observations.append({
                    "evidence_id": f"fact_{index}",
                    "tool": "upstream_evidence",
                    "summary": text,
                    "source_label": "accepted execution evidence",
                })
    return observations


__all__ = ["presentation_tool_observations"]
