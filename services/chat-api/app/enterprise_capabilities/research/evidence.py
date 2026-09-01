"""Reuse ASKAI's canonical research evidence contract for DSH capabilities."""

from __future__ import annotations

from typing import Any

from app.enterprise_capabilities.evidence.foundation import EvidenceNormalizer
from app.enterprise_capabilities.evidence.foundation.kb_qa_projection import sanitize_tool_results_for_evidence
from app.enterprise_capabilities.evidence.foundation.user_payload import build_user_evidence_payload


def build_research_evidence_bundle(
    *,
    tool_name: str,
    query: str,
    results: list[dict[str, Any]],
    raw_result: Any,
    evidence_sufficient: bool | None = None,
    budget_exhausted: bool = False,
    stop_reason: str = "",
) -> dict[str, Any]:
    """Project a DSH search result through the existing ASKAI evidence pipeline."""

    normalized_results: list[dict[str, Any]] = []
    for item in results[:32]:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        row.setdefault("tool", tool_name)
        if not row.get("source_url"):
            row["source_url"] = str(row.get("url") or row.get("source") or "")
        if not row.get("source"):
            row["source"] = str(row.get("source_url") or row.get("provider") or "")
        if not row.get("content"):
            row["content"] = str(row.get("snippet") or row.get("summary") or "")
        if not row.get("summary"):
            row["summary"] = str(row.get("snippet") or row.get("content") or "")
        normalized_results.append(row)

    bundle = EvidenceNormalizer.build_research_bundle(
        query=query,
        tools_used=[tool_name],
        results=normalized_results,
        raw_tool_results=sanitize_tool_results_for_evidence([
            {"tool": tool_name, "result": raw_result}
        ]),
    )
    if evidence_sufficient is not None:
        bundle["evidence_sufficient"] = bool(evidence_sufficient)
        bundle["budget_exhausted"] = bool(budget_exhausted)
        bundle["stop_reason"] = str(stop_reason or "")
        if not evidence_sufficient:
            bundle["open_questions"] = list(bundle.get("open_questions") or []) + [
                "The bounded research run did not establish sufficient evidence."
            ]
    return bundle


def public_evidence_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Return the existing bounded user-facing evidence projection."""

    return build_user_evidence_payload(bundle)


__all__ = ["build_research_evidence_bundle", "public_evidence_bundle"]
