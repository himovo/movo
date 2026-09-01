from __future__ import annotations

import json
from typing import Any, Dict, List


def decode_tool_payload(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("{") and text.endswith("}"):
            try:
                parsed = json.loads(text)
            except Exception:
                return {}
            if isinstance(parsed, dict):
                return parsed
    return {}


def is_internal_knowledge_qa_payload(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    provider = str(payload.get("provider") or "").strip().lower()
    mode = str(payload.get("mode") or "").strip().lower()
    return provider == "internal_knowledge_qa" or (
        mode == "qa" and ("usedChunks" in payload or "citations" in payload or "answer" in payload)
    )


def _clean_text(value: Any, *, limit: int = 0) -> str:
    text = str(value or "").strip()
    if limit and len(text) > limit:
        return text[:limit].rstrip()
    return text


def _compact_used_chunk(chunk: Any) -> Dict[str, Any]:
    if not isinstance(chunk, dict):
        return {}
    text = _clean_text(chunk.get("text") or chunk.get("content") or chunk.get("snippet") or "", limit=900)
    return {
        "citationId": _clean_text(chunk.get("citationId") or chunk.get("id"), limit=180),
        "documentId": _clean_text(chunk.get("documentId"), limit=120),
        "chunkId": _clean_text(chunk.get("chunkId"), limit=120),
        "title": _clean_text(chunk.get("title"), limit=180),
        "text": text,
        "score": chunk.get("score"),
        "pageNo": chunk.get("pageNo"),
    }


def _compact_citation(citation: Any) -> Dict[str, Any]:
    if not isinstance(citation, dict):
        return {}
    return {
        "documentId": _clean_text(citation.get("document_id") or citation.get("documentId"), limit=120),
        "chunkId": _clean_text(citation.get("chunk_id") or citation.get("chunkId"), limit=120),
        "titlePath": citation.get("title_path") or citation.get("titlePath") or [],
        "text": _clean_text(citation.get("text"), limit=900),
        "score": citation.get("score"),
        "pageNo": citation.get("page_no") or citation.get("pageNo"),
    }


def compact_kb_qa_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    used_chunks = [
        item
        for item in (_compact_used_chunk(chunk) for chunk in list(payload.get("usedChunks") or [])[:8])
        if item
    ]
    citations = [
        item
        for item in (_compact_citation(citation) for citation in list(payload.get("citations") or [])[:8])
        if item
    ]
    compact: Dict[str, Any] = {
        "ok": payload.get("ok"),
        "mode": payload.get("mode") or "qa",
        "provider": payload.get("provider") or "internal_knowledge_qa",
        "query": _clean_text(payload.get("query"), limit=500),
        "answer": _clean_text(payload.get("answer"), limit=6000),
        "usedCount": payload.get("usedCount") if payload.get("usedCount") is not None else len(used_chunks),
        "retrievedCount": payload.get("retrievedCount"),
        "usedChunks": used_chunks,
        "citations": citations,
    }
    evidence_bundle = payload.get("evidenceBundle")
    if isinstance(evidence_bundle, dict):
        compact["evidenceBundle"] = {
            "summary": _clean_text(evidence_bundle.get("summary"), limit=500),
            "sources": list(evidence_bundle.get("sources") or [])[:8],
        }
    return compact


def kb_qa_evidence_rows(tool_name: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not is_internal_knowledge_qa_payload(payload) or payload.get("ok") is False:
        return []
    answer = _clean_text(payload.get("answer"), limit=6000)
    used_chunks = list(payload.get("usedChunks") or [])
    used_count = payload.get("usedCount")
    if used_count is None:
        used_count = len(used_chunks)
    if not answer or int(used_count or 0) <= 0:
        return []
    return [
        {
            "tool": tool_name or "kb_search",
            "title": "内部知识库问答结论",
            "source": "内部知识库",
            "summary": answer,
            "content": answer,
            "meta": {
                "provider": payload.get("provider") or "internal_knowledge_qa",
                "mode": payload.get("mode") or "qa",
                "query": _clean_text(payload.get("query"), limit=500),
                "usedCount": used_count,
                "retrievedCount": payload.get("retrievedCount"),
                "usedChunks": compact_kb_qa_payload(payload).get("usedChunks") or [],
                "citations": compact_kb_qa_payload(payload).get("citations") or [],
            },
        }
    ]


def sanitize_tool_results_for_evidence(tool_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    sanitized: List[Dict[str, Any]] = []
    for record in list(tool_results or []):
        if not isinstance(record, dict):
            continue
        tool_name = str(record.get("tool") or "").strip()
        payload = decode_tool_payload(record.get("result"))
        if tool_name == "kb_search" and is_internal_knowledge_qa_payload(payload):
            sanitized.append({"tool": tool_name, "result": compact_kb_qa_payload(payload)})
            continue
        sanitized.append(dict(record))
    return sanitized
