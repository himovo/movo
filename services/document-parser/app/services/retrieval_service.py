from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.db import get_db
from app.domain.jobs import RetrievalSearchRequest
from app.services.embedding_provider import embed_query
from app.services.reranker_provider import rerank
from app.services.vector_store import get_vector_store

SETTINGS_COLLECTION = "knowledge_document_settings"
DOCUMENT_COLLECTION = "knowledge_documents"


def search_knowledge(request: RetrievalSearchRequest) -> dict[str, Any]:
    config = _effective_config(request.mainId)
    retrieval = dict(config.get("retrieval") or {})
    mode = request.retrievalMode or str(retrieval.get("mode") or "vector")
    top_n = int(request.topN or retrieval.get("topN") or 10)
    candidate_top_k = int(request.candidateTopK or retrieval.get("candidateTopK") or max(top_n, 50))
    score_threshold = float(retrieval.get("scoreThreshold") or 0)
    query_vector = embed_query(request.query, config)
    store = get_vector_store(config)
    candidates = store.search(
        query_vector=query_vector,
        query=request.query,
        main_id=request.mainId,
        knowledge_base_id=request.knowledgeBaseId,
        mode=mode,
        limit=candidate_top_k,
        score_threshold=score_threshold,
    )
    candidates = _filter_active_documents(candidates, request.mainId)
    candidates = _deduplicate(candidates, retrieval)
    use_rerank = bool((retrieval.get("rerank") or {}).get("enabled", False)) if request.rerank is None else bool(request.rerank)
    if use_rerank:
        rerank_config = dict(retrieval.get("rerank") or {})
        rerank_config["enabled"] = True
        config["retrieval"] = {**retrieval, "rerank": rerank_config}
        candidates = rerank(request.query, candidates, config)
    return {
        "query": request.query,
        "retrievalMode": mode,
        "topN": top_n,
        "items": candidates[:top_n],
        "total": len(candidates),
    }


def _filter_active_documents(items: list[dict[str, Any]], main_id: str) -> list[dict[str, Any]]:
    document_ids = sorted({str(item.get("documentId") or "") for item in items if str(item.get("documentId") or "")})
    if not document_ids:
        return []
    active_ids = {
        str(doc.get("_id") or "")
        for doc in get_db()[DOCUMENT_COLLECTION].find(
            {
                "_id": {"$in": document_ids},
                "main_id": main_id,
                "deleted_at": None,
            },
            {"_id": 1},
        )
    }
    if not active_ids:
        return []
    return [item for item in items if str(item.get("documentId") or "") in active_ids]


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
        "scoreThreshold": 0,
        "metadataFiltersEnabled": True,
        "maxChunksPerDocument": 5,
        "dedupByDocument": True,
        **dict(config.get("retrieval") or {}),
        "rerank": rerank_config,
    }
    config["_mainId"] = main_id
    return config


def _deduplicate(items: list[dict[str, Any]], retrieval: dict[str, Any]) -> list[dict[str, Any]]:
    if not bool(retrieval.get("dedupByDocument", True)):
        return items
    max_per_doc = max(1, int(retrieval.get("maxChunksPerDocument") or 5))
    counts: dict[str, int] = {}
    output: list[dict[str, Any]] = []
    for item in items:
        document_id = str(item.get("documentId") or "")
        count = counts.get(document_id, 0)
        if count >= max_per_doc:
            continue
        counts[document_id] = count + 1
        output.append(item)
    return output
