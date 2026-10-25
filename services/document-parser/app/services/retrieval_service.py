from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.db import get_db
from app.domain.jobs import RetrievalSearchRequest
from app.services.embedding_provider import embed_query
from app.services.reranker_provider import rerank
from app.services.retrieval_access_policy import knowledge_retrieval_access_policy
from app.services.vector_store import get_vector_store
from app.services.exact_identifier_retrieval import exact_identifier_candidates
from app.services.retrieval_selection import distinct_chunks, fuse_candidate_sources, select_final_chunks
from app.services.retrieval_trace import trace_stage

SETTINGS_COLLECTION = "knowledge_document_settings"


def search_knowledge(request: RetrievalSearchRequest) -> dict[str, Any]:
    config = _effective_config(request.mainId)
    retrieval = dict(config.get("retrieval") or {})
    mode = request.retrievalMode or str(retrieval.get("mode") or "vector")
    top_n = int(request.topN or retrieval.get("topN") or 10)
    candidate_top_k = int(request.candidateTopK or retrieval.get("candidateTopK") or max(top_n, 50))
    score_threshold = float(retrieval.get("scoreThreshold") or 0)
    query_vector = embed_query(request.query, config)
    store = get_vector_store(config)
    candidates = _search_authorized_candidates(
        store=store,
        query_vector=query_vector,
        query=request.query,
        main_id=request.mainId,
        user_id=request.userId,
        knowledge_base_id=request.knowledgeBaseId,
        mode=mode,
        top_n=top_n,
        candidate_top_k=candidate_top_k,
        max_candidate_scan=int(retrieval.get("maxCandidateScan") or 10_000),
        score_threshold=score_threshold,
    )
    trace_stage("authorized_candidates", candidates)
    exact = exact_identifier_candidates(
        request.query, main_id=request.mainId, user_id=request.userId,
        knowledge_base_id=request.knowledgeBaseId,
    )
    trace_stage("lexical_candidates", exact)
    candidates = fuse_candidate_sources(distinct_chunks(candidates), exact)
    use_rerank = bool((retrieval.get("rerank") or {}).get("enabled", False)) if request.rerank is None else bool(request.rerank)
    if use_rerank:
        rerank_config = dict(retrieval.get("rerank") or {})
        rerank_config["enabled"] = True
        rerank_config["topK"] = max(top_n, int(rerank_config.get("topK") or 0))
        config["retrieval"] = {**retrieval, "rerank": rerank_config}
        candidates = rerank(request.query, candidates, config)
    trace_stage("ranked_candidates", candidates)
    candidate_total = len(candidates)
    candidates = select_final_chunks(candidates, top_n=top_n)
    trace_stage("final_context", candidates)
    return {
        "query": request.query,
        "retrievalMode": mode,
        "topN": top_n,
        "items": candidates,
        "total": candidate_total,
    }


def _search_authorized_candidates(
    *,
    store: Any,
    query_vector: list[float],
    query: str,
    main_id: str,
    user_id: str,
    knowledge_base_id: str,
    mode: str,
    top_n: int,
    candidate_top_k: int,
    max_candidate_scan: int,
    score_threshold: float,
) -> list[dict[str, Any]]:
    """Scan tenant-ranked candidates in pages and authorize each page in bulk."""
    target = max(top_n, candidate_top_k)
    page_size = min(500, max(50, candidate_top_k))
    scan_limit = max(page_size, max_candidate_scan)
    offset = 0
    authorized: list[dict[str, Any]] = []
    while offset < scan_limit:
        limit = min(page_size, scan_limit - offset)
        raw = store.search(
            query_vector=query_vector,
            query=query,
            main_id=main_id,
            knowledge_base_id=knowledge_base_id,
            mode=mode,
            limit=limit,
            offset=offset,
            score_threshold=score_threshold,
        )
        authorized.extend(knowledge_retrieval_access_policy.filter_candidates(
            raw, main_id=main_id, user_id=user_id,
        ))
        if len(authorized) >= target or len(raw) < limit:
            break
        offset += len(raw)
    return authorized


def _filter_active_documents(
    items: list[dict[str, Any]],
    main_id: str,
    *,
    user_id: str = "",
    knowledge_base_id: str = "",
) -> list[dict[str, Any]]:
    # Compatibility wrapper for focused tests and older callers. Authorization
    # no longer depends on whether a resource id was explicitly supplied.
    return knowledge_retrieval_access_policy.filter_candidates(
        items, main_id=main_id, user_id=user_id,
    )


def _effective_config(main_id: str) -> dict[str, Any]:
    doc = get_db()[SETTINGS_COLLECTION].find_one({"main_id": main_id, "kind": "knowledge"})
    config = dict((doc or {}).get("config") or {})
    config.setdefault("embedding", {})
    config.setdefault("vectorStore", {})
    config.setdefault("retrieval", {})
    config["embedding"] = {
        "provider": "model_center",
        "modelInstanceId": "",
        "dimension": 1536,
        "batchSize": 32,
        "timeoutSeconds": 30,
        **dict(config.get("embedding") or {}),
    }
    config["vectorStore"] = {
        "type": "weaviate",
        "endpoint": settings.weaviate_endpoint,
        "apiKey": settings.weaviate_api_key,
        "collectionName": settings.weaviate_collection_name,
        "distanceMetric": settings.weaviate_distance_metric,
        **dict(config.get("vectorStore") or {}),
    }
    rerank_config = {
        "enabled": False,
        "provider": "model_center",
        "modelInstanceId": "",
        "model": "",
        "endpoint": "",
        "topK": 20,
        "scoreThreshold": 0,
        "timeoutSeconds": 10,
        "fallbackPolicy": "return_vector_results",
        **dict((config.get("retrieval") or {}).get("rerank") or {}),
    }
    config["retrieval"] = {
        "mode": "vector",
        "topN": 10,
        "candidateTopK": 50,
        "maxCandidateScan": 10000,
        "scoreThreshold": 0,
        "metadataFiltersEnabled": True,
        **dict(config.get("retrieval") or {}),
        "rerank": rerank_config,
    }
    config["_mainId"] = main_id
    return config
