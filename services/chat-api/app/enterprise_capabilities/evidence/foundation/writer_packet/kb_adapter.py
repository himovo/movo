from __future__ import annotations

from typing import Any, Dict, List

from app.enterprise_capabilities.evidence.foundation.kb_document_sources import extract_kb_document_sources
from app.enterprise_capabilities.evidence.foundation.kb_qa_projection import decode_tool_payload, kb_qa_evidence_rows

from .common import fingerprint, text


def _rows_from_record(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    payload = decode_tool_payload(record.get("result"))
    if payload:
        rows = kb_qa_evidence_rows(text(record.get("tool")) or "kb_search", payload)
        if rows:
            return rows
    return [record]


def build_kb_materials(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    excerpts: List[Dict[str, Any]] = []
    citations: List[Dict[str, Any]] = []
    evidence_items: List[Dict[str, Any]] = []
    seen_excerpts: set[str] = set()
    seen_citations: set[str] = set()
    expected_citation_keys: set[str] = set()
    for record in records:
        for row in _rows_from_record(record):
            summary = text(row.get("summary") or row.get("content"))
            if summary:
                item = {
                    "source_type": "kb",
                    "title": text(row.get("title")) or "内部知识库",
                    "summary": summary,
                    "source": text(row.get("source")) or "内部知识库",
                }
                token = fingerprint(item)
                if token not in seen_excerpts:
                    seen_excerpts.add(token)
                    evidence_items.append(item)
            meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
            expected_sources: List[Any] = []
            expected_sources.extend(list(meta.get("usedChunks") or meta.get("used_chunks") or []))
            expected_sources.extend(list(meta.get("citations") or []))
            nested_bundle = meta.get("evidenceBundle") or meta.get("evidence_bundle")
            if isinstance(nested_bundle, dict):
                expected_sources.extend(list(nested_bundle.get("sources") or []))
            for source in expected_sources:
                if not isinstance(source, dict):
                    continue
                document_id = text(source.get("document_id") or source.get("documentId"))
                chunk_id = text(source.get("chunk_id") or source.get("chunkId"))
                if document_id and chunk_id:
                    expected_citation_keys.add(f"{document_id}:{chunk_id}")

            for source in extract_kb_document_sources(row):
                citation_key = f"{source.get('document_id') or ''}:{source.get('chunk_id') or ''}"
                if citation_key in seen_citations:
                    continue
                seen_citations.add(citation_key)
                citation = {
                    "source_type": "kb",
                    "citation_id": text(source.get("citation_id") or source.get("id")),
                    "document_id": text(source.get("document_id")),
                    "chunk_id": text(source.get("chunk_id")),
                    "title": text(source.get("title")),
                    "page_no": source.get("page_no"),
                    "source_anchor": source.get("source_anchor") or {},
                }
                citations.append(citation)
                content = text(source.get("content") or source.get("snippet"))
                if content:
                    excerpts.append({**citation, "content": content})
    return {
        "source_excerpts": excerpts,
        "citations": citations,
        "evidence_items": evidence_items,
        "expected_citation_keys": sorted(expected_citation_keys),
    }
