from __future__ import annotations

from typing import Any

from app.core.db import get_db
from app.domain.jobs import IndexDocumentJobRequest
from app.integrations.callbacks.admin_api_client import post_callback
from app.repositories.job_repository import mark_job_succeeded, update_job_progress
from app.services.embedding_provider import embed_texts
from app.services.vector_store import get_vector_store

CHUNK_COLLECTION = "knowledge_document_chunks"


def run_document_index(job_id: str, request: IndexDocumentJobRequest) -> None:
    db = get_db()
    query = {
        "main_id": request.mainId,
        "document_id": request.documentId,
        "chunk_stage": request.chunkStage,
    }
    chunks = list(db[CHUNK_COLLECTION].find(query).sort("ordinal", 1))
    if not chunks:
        raise RuntimeError("没有可索引的 RAG 分段")

    config = dict(request.config or {})
    config["_mainId"] = request.mainId
    vector_store = get_vector_store(config)
    vector_store.ensure_schema()
    update_job_progress(job_id, 20)

    index_config = dict(config.get("index") or {})
    batch_size = max(1, min(int(index_config.get("batchSize") or 32), 256))
    total = len(chunks)
    indexed = 0
    for start in range(0, total, batch_size):
        batch = chunks[start : start + batch_size]
        texts = [_chunk_embedding_text(item, config) for item in batch]
        vectors = embed_texts(texts, config)
        vector_store.upsert_chunks(batch, vectors)
        ids = [item["_id"] for item in batch]
        db[CHUNK_COLLECTION].update_many(
            {"_id": {"$in": ids}},
            {
                "$set": {
                    "embedding_status": "embedded",
                    "index_status": "indexed",
                    "vector_store_type": "weaviate",
                    "vector_collection_name": vector_store.collection,
                }
            },
        )
        indexed += len(batch)
        update_job_progress(job_id, 20 + int(indexed / total * 70))

    result = {
        "indexedChunkCount": indexed,
        "vectorStoreType": "weaviate",
        "collectionName": vector_store.collection,
    }
    post_callback(
        request.callback.url,
        request.callback.token,
        {
            "jobId": job_id,
            "status": "succeeded",
            **result,
            "error": "",
        },
    )
    mark_job_succeeded(job_id, result)


def post_index_failure_callback(job_id: str, request: IndexDocumentJobRequest, message: str) -> None:
    try:
        post_callback(
            request.callback.url,
            request.callback.token,
            {
                "jobId": job_id,
                "status": "failed",
                "indexedChunkCount": 0,
                "vectorStoreType": str((request.config.get("vectorStore") or {}).get("type") or "weaviate"),
                "collectionName": str((request.config.get("vectorStore") or {}).get("collectionName") or ""),
                "error": message[:2000],
            },
        )
    except Exception:
        return


def _chunk_embedding_text(chunk: dict[str, Any], config: dict[str, Any]) -> str:
    context = dict(config.get("context") or {})
    parts: list[str] = []
    if bool(context.get("includeTitlePath", True)):
        parts.extend([str(item) for item in chunk.get("title_path") or [] if str(item).strip()])
    if bool(context.get("includePageNo", True)) and chunk.get("page_no") is not None:
        parts.append(f"第 {chunk.get('page_no')} 页")
    parts.append(str(chunk.get("contextual_text") or chunk.get("text") or ""))
    return "\n".join(part for part in parts if part.strip())
