from __future__ import annotations

from typing import Any, Dict, List

from app.knowledge.api.schemas import KnowledgeChunk, KnowledgeCitation, KnowledgeQARequest, KnowledgeQAResult
from app.knowledge.citations.citation_resolver import build_evidence_bundle


def _model_dump(value: Any) -> Dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return dict(value)
    return {}


def _coerce_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _chunk_title(chunk: KnowledgeChunk) -> str:
    return " / ".join([str(item).strip() for item in chunk.title_path if str(item).strip()]) or chunk.chunk_id


def _chunk_to_used_payload(chunk: KnowledgeChunk) -> Dict[str, Any]:
    text = str(chunk.contextual_text or chunk.text or "").strip()
    citation_id = f"{chunk.document_id}:{chunk.chunk_id}"
    return {
        "id": citation_id,
        "citationId": citation_id,
        "documentId": chunk.document_id,
        "chunkId": chunk.chunk_id,
        "chunkStage": chunk.chunk_stage,
        "title": _chunk_title(chunk),
        "titlePath": list(chunk.title_path or []),
        "text": text,
        "pageNo": chunk.page_no,
        "contentType": chunk.content_type,
        "sourceChunkIds": list(chunk.source_chunk_ids or []),
        "score": chunk.score,
        "rerankScore": chunk.rerank_score,
        "distance": chunk.distance,
        "metadata": dict(chunk.metadata or {}),
    }


def _citation_to_used_payload(citation: KnowledgeCitation) -> Dict[str, Any]:
    text = str(citation.text or "").strip()
    citation_id = f"{citation.document_id}:{citation.chunk_id}"
    return {
        "id": citation_id,
        "citationId": citation_id,
        "documentId": citation.document_id,
        "chunkId": citation.chunk_id,
        "chunkStage": str(citation.source_anchor.get("chunkStage") or "rag"),
        "title": " / ".join([str(item).strip() for item in citation.title_path if str(item).strip()]) or citation.chunk_id,
        "titlePath": list(citation.title_path or []),
        "text": text,
        "pageNo": citation.page_no,
        "contentType": citation.content_type,
        "sourceChunkIds": list(citation.source_chunk_ids or []),
        "score": citation.score,
        "distance": None,
        "metadata": {"sourceAnchor": dict(citation.source_anchor or {})},
    }


def _used_chunks(result: KnowledgeQAResult) -> List[Dict[str, Any]]:
    citations = list(result.citations or [])
    if citations:
        return [_citation_to_used_payload(item) for item in citations]
    used_ids = [str(item).strip() for item in list(result.used_chunk_ids or []) if str(item).strip()]
    chunks = list(result.retrieved_chunks or [])
    by_citation_id = {f"{chunk.document_id}:{chunk.chunk_id}": chunk for chunk in chunks}
    by_chunk_id: Dict[str, KnowledgeChunk] = {}
    duplicate_chunk_ids: set[str] = set()
    for chunk in chunks:
        if chunk.chunk_id in by_chunk_id:
            duplicate_chunk_ids.add(chunk.chunk_id)
            continue
        by_chunk_id[chunk.chunk_id] = chunk
    output: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for used_id in used_ids:
        if used_id in seen:
            continue
        chunk = by_citation_id.get(used_id)
        if chunk is None and used_id not in duplicate_chunk_ids:
            chunk = by_chunk_id.get(used_id)
        if not chunk:
            continue
        seen.add(used_id)
        output.append(_chunk_to_used_payload(chunk))
    return output


def _used_chunks_as_results(used_chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compatibility shape for existing evidence extraction.

    This intentionally mirrors only the selected chunks, not the original
    retrieval topN candidate set.
    """
    rows: List[Dict[str, Any]] = []
    for chunk in list(used_chunks or []):
        chunk_id = str(chunk.get("chunkId") or "").strip()
        citation_id = str(chunk.get("citationId") or chunk.get("id") or "").strip()
        rows.append(
            {
                "source": f"kb://{citation_id or chunk_id or 'chunk'}",
                "title": str(chunk.get("title") or chunk_id or "内部知识库").strip(),
                "content": str(chunk.get("text") or "").strip(),
                "score": chunk.get("score"),
                "meta": {
                    "provider": "internal_knowledge_qa",
                    "citationId": citation_id,
                    "documentId": chunk.get("documentId"),
                    "chunkId": chunk_id,
                    "chunkStage": chunk.get("chunkStage"),
                    "pageNo": chunk.get("pageNo"),
                    "contentType": chunk.get("contentType"),
                    "sourceChunkIds": chunk.get("sourceChunkIds") or [],
                    "titlePath": chunk.get("titlePath") or [],
                },
            }
        )
    return rows


class InternalKnowledgeQAService:
    """QA-mode internal knowledge tool service.

    The graph/tool contract returns the final answer plus the chunks selected by
    the QA model. It does not expose raw topN retrieval candidates by default.
    """

    async def answer(
        self,
        *,
        query: str,
        user_id: str = "",
        main_id: str = "",
        session_id: str = "",
        knowledge_ids: Any = None,
        top_k: int = 8,
    ) -> Dict[str, Any]:
        q = str(query or "").strip()
        if not q:
            empty_evidence = {
                "summary": "内部知识问答检索到 0 条引用来源",
                "sources": [],
                "confirmed_facts": [],
                "open_questions": [],
            }
            return {
                "ok": False,
                "error": "missing_query",
                "mode": "qa",
                "provider": "internal_knowledge_qa",
                "query": q,
                "answer": "",
                "usedChunks": [],
                "citations": [],
                "evidenceBundle": empty_evidence,
                "retrievedCount": 0,
                "results": [],
            }

        request = KnowledgeQARequest(
            query=q,
            user_id=str(user_id or "").strip(),
            main_id=str(main_id or "").strip() or "default",
            session_id=str(session_id or "").strip(),
            knowledge_base_ids=_coerce_list(knowledge_ids),
            top_n=max(1, min(50, int(top_k or 8))),
        )
        from app.knowledge.agents.knowledge_qa_agent import knowledge_qa_agent

        result = await knowledge_qa_agent.answer(request)
        used_chunks = _used_chunks(result)
        citations = [_model_dump(item) for item in list(result.citations or [])]
        evidence_bundle = build_evidence_bundle(q, list(result.citations or []))
        return {
            "ok": True,
            "mode": "qa",
            "provider": "internal_knowledge_qa",
            "query": q,
            "user_id": request.user_id,
            "main_id": request.main_id,
            "session_id": request.session_id,
            "knowledge_ids": list(request.knowledge_base_ids or []),
            "answer": result.answer,
            "usedChunks": used_chunks,
            "citations": citations,
            "evidenceBundle": evidence_bundle,
            "retrievedCount": len(list(result.retrieved_chunks or [])),
            "usedCount": len(used_chunks),
            "results": _used_chunks_as_results(used_chunks),
        }


internal_knowledge_qa_service = InternalKnowledgeQAService()
