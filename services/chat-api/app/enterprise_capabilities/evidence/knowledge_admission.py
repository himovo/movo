"""Admission policy for turning retrieval candidates into user-visible evidence.

Knowledge retrieval intentionally returns a wider candidate set to the agent.  A
candidate is not, however, automatically strong enough to be presented to the
user as evidence.  This module owns that boundary and is deliberately separate
from retrieval ranking and UI projection.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any


@dataclass(frozen=True, slots=True)
class KnowledgeEvidenceAdmissionPolicy:
    """Conservative defaults for normalized vector/rerank relevance scores."""

    minimum_score: float = 0.05
    minimum_top_score_ratio: float = 0.15
    continuity_minimum_score: float = 0.02
    continuity_top_score_ratio: float = 0.05


@dataclass(frozen=True, slots=True)
class KnowledgeEvidenceAdmission:
    admitted: tuple[dict[str, Any], ...]
    rejected: tuple[dict[str, Any], ...]
    strong_threshold: float | None
    strategy: str


DEFAULT_KNOWLEDGE_EVIDENCE_POLICY = KnowledgeEvidenceAdmissionPolicy()


def _score(item: dict[str, Any]) -> float | None:
    raw = item.get("rerankScore")
    if raw is None:
        raw = item.get("score")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _document_key(item: dict[str, Any]) -> str:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    return str(
        item.get("documentId")
        or metadata.get("document_id")
        or metadata.get("object_path")
        or ""
    ).strip()


def admit_knowledge_evidence(
    items: list[dict[str, Any]],
    *,
    policy: KnowledgeEvidenceAdmissionPolicy = DEFAULT_KNOWLEDGE_EVIDENCE_POLICY,
) -> KnowledgeEvidenceAdmission:
    """Select reliable evidence while preserving the original candidate order.

    The strong gate combines an absolute noise floor with a threshold relative
    to the best hit.  A weaker continuity gate may retain adjacent evidence from
    a document that already has a strong hit.  Mixed scored/unscored candidates
    never promote unscored rows; fully unscored legacy results retain their
    previous behaviour because no comparable relevance signal exists.
    """

    candidates = [item for item in items if isinstance(item, dict)]
    scored = [(item, score) for item in candidates if (score := _score(item)) is not None]
    if not scored:
        return KnowledgeEvidenceAdmission(tuple(candidates), (), None, "unscored_compatibility")

    top_score = max(score for _, score in scored)
    strong_threshold = max(policy.minimum_score, top_score * policy.minimum_top_score_ratio)
    strong_ids = {id(item) for item, score in scored if score >= strong_threshold}
    strong_documents = {
        key for item, score in scored
        if score >= strong_threshold and (key := _document_key(item))
    }
    continuity_threshold = max(
        policy.continuity_minimum_score,
        top_score * policy.continuity_top_score_ratio,
    )

    admitted_ids = set(strong_ids)
    for item, score in scored:
        if (
            id(item) not in admitted_ids
            and score >= continuity_threshold
            and _document_key(item) in strong_documents
        ):
            admitted_ids.add(id(item))

    admitted = tuple(item for item in candidates if id(item) in admitted_ids)
    rejected = tuple(item for item in candidates if id(item) not in admitted_ids)
    return KnowledgeEvidenceAdmission(admitted, rejected, strong_threshold, "scored_adaptive")


__all__ = [
    "DEFAULT_KNOWLEDGE_EVIDENCE_POLICY",
    "KnowledgeEvidenceAdmission",
    "KnowledgeEvidenceAdmissionPolicy",
    "admit_knowledge_evidence",
]
