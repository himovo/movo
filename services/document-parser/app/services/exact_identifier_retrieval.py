"""Recover table rows and clauses addressed by an exact business identifier."""

from __future__ import annotations

from typing import Any

from app.core.db import get_db
from app.services.chunk_identifiers import extract_identifiers
from app.services.retrieval_access_policy import knowledge_retrieval_access_policy


def exact_identifier_candidates(
    query: str, *, main_id: str, user_id: str, knowledge_base_id: str, limit: int = 30,
) -> list[dict[str, Any]]:
    identifiers = extract_identifiers(query)[:3]
    if not identifiers:
        return []
    db = get_db()
    selector: dict[str, Any] = {
        "main_id": main_id,
        "chunk_stage": "rag",
        "search_identifiers": {"$in": identifiers},
    }
    if knowledge_base_id:
        selector["knowledge_base_id"] = knowledge_base_id
    target = max(1, min(limit, 50))
    authorized: list[dict[str, Any]] = []
    batch: list[dict[str, Any]] = []
    # Authorization happens after the indexed lookup. Scan beyond denied rows
    # so they cannot crowd out a later row the caller is allowed to read.
    for scanned, row in enumerate(db.knowledge_document_chunks.find(selector).limit(1000), start=1):
        batch.append(_as_retrieval_item(row))
        if len(batch) < 50 and scanned < 1000:
            continue
        authorized.extend(knowledge_retrieval_access_policy.filter_candidates(
            batch, main_id=main_id, user_id=user_id,
        ))
        batch = []
        if len(authorized) >= target:
            break
    if batch and len(authorized) < target:
        authorized.extend(knowledge_retrieval_access_policy.filter_candidates(
            batch, main_id=main_id, user_id=user_id,
        ))
    return authorized[:target]


def _as_retrieval_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "documentId": str(row.get("document_id") or ""),
        "chunkId": str(row.get("chunk_id") or ""),
        "chunkStage": "rag",
        "text": str(row.get("text") or ""),
        "contextualText": str(row.get("contextual_text") or row.get("text") or ""),
        "titlePath": list(row.get("title_path") or []),
        "pageNo": row.get("page_no"),
        "contentType": str(row.get("content_type") or "text"),
        "sourceChunkIds": list(row.get("source_chunk_ids") or []),
        "ordinal": int(row.get("ordinal") or 0),
        "score": 1.0,
        "matchType": "exact_identifier",
        "distance": None,
    }
