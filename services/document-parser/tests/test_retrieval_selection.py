from __future__ import annotations

from app.services import retrieval_service
from app.services.reranker_provider import _merge_results
from app.services.retrieval_selection import fuse_candidate_sources


def _item(document: str, chunk: int, score: float = 0.0) -> dict:
    return {"documentId": document, "chunkId": f"chunk_{chunk:06d}", "score": score, "text": f"clause {chunk}"}


def test_later_clause_is_available_to_rerank_before_context_budget(monkeypatch):
    vector_hits = [_item("policy", number, 1 - number / 100) for number in range(1, 9)]
    vector_hits += [_item("other", 1, 0.5)]
    seen_by_reranker: list[str] = []

    monkeypatch.setattr(retrieval_service, "_effective_config", lambda _: {
        "retrieval": {"rerank": {"enabled": True}},
    })
    monkeypatch.setattr(retrieval_service, "embed_query", lambda *_: [0.1])
    monkeypatch.setattr(retrieval_service, "get_vector_store", lambda *_: object())
    monkeypatch.setattr(retrieval_service, "_search_authorized_candidates", lambda **_: list(vector_hits))
    monkeypatch.setattr(retrieval_service, "exact_identifier_candidates", lambda *_, **__: [])

    def rerank(_query, candidates, _config):
        seen_by_reranker.extend(item["chunkId"] for item in candidates)
        assert _config["retrieval"]["rerank"]["topK"] >= 5
        return [candidates[6], *[item for index, item in enumerate(candidates) if index != 6]]

    monkeypatch.setattr(retrieval_service, "rerank", rerank)
    result = retrieval_service.search_knowledge(retrieval_service.RetrievalSearchRequest(
        query="Can this category of person apply?", mainId="tenant", userId="user", topN=5,
    ))
    assert "chunk_000007" in seen_by_reranker
    assert result["items"][0]["chunkId"] == "chunk_000007"
    assert len(result["items"]) == 5


def test_lexical_candidate_enters_rerank_without_bypassing_its_order(monkeypatch):
    seen = []
    monkeypatch.setattr(retrieval_service, "_effective_config", lambda _: {"retrieval": {"rerank": {"enabled": True}}})
    monkeypatch.setattr(retrieval_service, "embed_query", lambda *_: [0.1])
    monkeypatch.setattr(retrieval_service, "get_vector_store", lambda *_: object())
    monkeypatch.setattr(retrieval_service, "_search_authorized_candidates", lambda **_: [_item("a", 1)])
    monkeypatch.setattr(retrieval_service, "exact_identifier_candidates", lambda *_, **__: [_item("b", 2)])

    def rerank(_query, candidates, _config):
        seen.extend(item["chunkId"] for item in candidates)
        return sorted(candidates, key=lambda item: item["documentId"])

    monkeypatch.setattr(retrieval_service, "rerank", rerank)
    result = retrieval_service.search_knowledge(retrieval_service.RetrievalSearchRequest(
        query="project code", mainId="tenant", userId="user", topN=2,
    ))
    assert seen == ["chunk_000001", "chunk_000002"]
    assert [item["chunkId"] for item in result["items"]] == ["chunk_000001", "chunk_000002"]


def test_context_budget_does_not_impose_per_document_limit(monkeypatch):
    monkeypatch.setattr(retrieval_service, "_effective_config", lambda _: {"retrieval": {"rerank": {"enabled": False}}})
    monkeypatch.setattr(retrieval_service, "embed_query", lambda *_: [0.1])
    monkeypatch.setattr(retrieval_service, "get_vector_store", lambda *_: object())
    monkeypatch.setattr(retrieval_service, "_search_authorized_candidates", lambda **_: [_item("a", i) for i in range(8)])
    monkeypatch.setattr(retrieval_service, "exact_identifier_candidates", lambda *_, **__: [])
    result = retrieval_service.search_knowledge(retrieval_service.RetrievalSearchRequest(
        query="apply conditions", mainId="tenant", userId="user", topN=8,
    ))
    assert len(result["items"]) == 8


def test_reranker_zero_based_document_index_is_kept():
    candidates = [_item("a", 1), _item("b", 2)]
    result = _merge_results(candidates, [{"document_index": 0, "relevance_score": 0.8}], top_n=2, threshold=0)
    assert [item["chunkId"] for item in result] == ["chunk_000001"]


def test_fusion_rewards_evidence_found_by_both_methods_without_duplication():
    shared = _item("a", 1)
    semantic = [shared, _item("a", 2)]
    lexical = [_item("b", 3), shared]
    result = fuse_candidate_sources(semantic, lexical)
    assert [item["chunkId"] for item in result] == ["chunk_000001", "chunk_000003", "chunk_000002"]
    assert result[0]["matchType"] == "exact_identifier"
