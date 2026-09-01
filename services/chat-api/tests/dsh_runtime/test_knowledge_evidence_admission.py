from __future__ import annotations

from app.enterprise_capabilities.evidence.knowledge_admission import admit_knowledge_evidence


def _item(document_id: str, score: float | None) -> dict:
    item = {
        "documentId": document_id,
        "chunkId": f"chunk-{document_id}-{score}",
        "contextualText": f"content from {document_id}",
    }
    if score is not None:
        item["score"] = score
    return item


def test_rejects_low_score_tail_from_an_unrelated_document() -> None:
    candidates = [
        _item("token-report", 0.7176740400350329),
        _item("token-report", 0.39212327124471413),
        _item("token-report", 0.2485870671359841),
        _item("token-report", 0.19698542092259758),
        _item("movo-acceptance", 0.005949579483329656),
    ]

    decision = admit_knowledge_evidence(candidates)

    assert [item["documentId"] for item in decision.admitted] == ["token-report"] * 4
    assert [item["documentId"] for item in decision.rejected] == ["movo-acceptance"]
    assert decision.strategy == "scored_adaptive"


def test_preserves_weaker_continuity_from_an_admitted_document() -> None:
    candidates = [
        _item("product-guide", 0.8),
        _item("product-guide", 0.06),
        _item("other-document", 0.06),
    ]

    decision = admit_knowledge_evidence(candidates)

    assert list(decision.admitted) == candidates[:2]
    assert list(decision.rejected) == candidates[2:]


def test_does_not_present_uniformly_low_scored_candidates_as_evidence() -> None:
    candidates = [_item("noise-a", 0.04), _item("noise-b", 0.01)]

    decision = admit_knowledge_evidence(candidates)

    assert decision.admitted == ()
    assert list(decision.rejected) == candidates


def test_unscored_legacy_results_remain_compatible() -> None:
    candidates = [_item("legacy-a", None), _item("legacy-b", None)]

    decision = admit_knowledge_evidence(candidates)

    assert list(decision.admitted) == candidates
    assert decision.strategy == "unscored_compatibility"


def test_prefers_rerank_score_when_available() -> None:
    strong = _item("reranked", 0.001)
    strong["rerankScore"] = 0.9
    weak = _item("vector-only", 0.01)

    decision = admit_knowledge_evidence([strong, weak])

    assert list(decision.admitted) == [strong]
    assert list(decision.rejected) == [weak]
