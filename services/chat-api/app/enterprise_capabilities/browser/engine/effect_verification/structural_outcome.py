"""Collect site-independent DOM structure changes after a browser commit."""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation

from .contracts import EffectEvidence


_COLLECTION_ITEM_ROLES = frozenset({
    "article", "listitem", "row", "treeitem", "option", "feeditem",
})


def collect_structural_outcome_evidence(
    before: Observation,
    after: Observation,
) -> List[EffectEvidence]:
    """Describe collection growth without interpreting page language."""
    before_counts = _collection_role_counts(before.elements)
    after_counts = _collection_role_counts(after.elements)
    evidence: List[EffectEvidence] = []
    for role, after_count in after_counts.items():
        before_count = before_counts.get(role, 0)
        if after_count <= before_count:
            continue
        evidence.append(EffectEvidence(
            evidence_id=f"collection:{role}:{before_count}:{after_count}",
            kind="collection_count_increased",
            detail=f"collection role {role} count changed {before_count} -> {after_count}",
            polarity="positive",
            weight=0.45,
        ))
    return evidence[:8]


def _collection_role_counts(elements: Iterable[Dict[str, Any]]) -> Counter[str]:
    return Counter(
        str(item.get("role") or "").strip().lower()
        for item in elements
        if isinstance(item, dict)
        and not item.get("editable")
        and str(item.get("role") or "").strip().lower() in _COLLECTION_ITEM_ROLES
    )


__all__ = ["collect_structural_outcome_evidence"]
