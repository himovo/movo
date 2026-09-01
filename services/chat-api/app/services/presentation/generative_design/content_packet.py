from __future__ import annotations

from typing import Any, Dict, List

from app.services.presentation.contracts import ConstraintBundle, PageBrief


def _compact_strings(values: List[Any], *, limit: int) -> List[str]:
    result: List[str] = []
    for value in list(values or []):
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def build_content_packet(
    *,
    page_brief: PageBrief,
    constraint_bundle: ConstraintBundle,
) -> Dict[str, Any]:
    """Build a compact semantic packet without pre-shaping content as cards.

    The page composer should decide whether an idea becomes type, a symbol, a
    relationship, a band, or a peer module. Keeping the packet semantic avoids
    biasing every page toward the same UI-like component grammar.
    """

    observations: List[Dict[str, str]] = []
    for raw in list(constraint_bundle.tool_observations or [])[:6]:
        if not isinstance(raw, dict):
            continue
        summary = str(raw.get("summary") or "").strip()
        if not summary:
            continue
        observations.append({
            "evidence_id": str(raw.get("evidence_id") or "").strip(),
            "source_label": str(raw.get("source_label") or "").strip(),
            "summary": summary,
        })

    return {
        "page_id": str(page_brief.page_id or "").strip(),
        "page_type": str(page_brief.page_type or "content").strip(),
        "primary_claim": str(page_brief.key_takeaway or page_brief.page_goal or "").strip(),
        "communication_goal": str(page_brief.page_goal or "").strip(),
        "supporting_ideas": _compact_strings(list(page_brief.must_include or []), limit=6),
        "relationships_to_visualize": _compact_strings(list(page_brief.must_visualize or []), limit=5),
        "narrative_role": str(page_brief.narrative_role or "").strip(),
        "source_intent": str(page_brief.source_user_intent or "").strip(),
        "evidence": observations,
        "must_avoid": _compact_strings(list(page_brief.must_avoid or []), limit=6),
    }


__all__ = ["build_content_packet"]
