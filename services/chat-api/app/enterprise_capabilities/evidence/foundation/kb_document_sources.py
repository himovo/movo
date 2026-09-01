from __future__ import annotations

from typing import Any, Dict, List


def _text(value: Any, *, limit: int = 0) -> str:
    text = str(value or "").strip()
    if limit and len(text) > limit:
        return text[:limit].rstrip()
    return text


def _first_text(*values: Any, limit: int = 0) -> str:
    for value in values:
        text = _text(value, limit=limit)
        if text:
            return text
    return ""


def _title_from_path(value: Any) -> str:
    if isinstance(value, list):
        return " / ".join(_text(item) for item in value if _text(item))
    return ""


def _normalize_document_source(source: Dict[str, Any], *, fallback_id: str) -> Dict[str, Any]:
    document_id = _first_text(source.get("document_id"), source.get("documentId"), limit=160)
    chunk_id = _first_text(source.get("chunk_id"), source.get("chunkId"), limit=180)
    if not document_id or not chunk_id:
        return {}

    citation_id = _first_text(
        source.get("citation_id"),
        source.get("citationId"),
        source.get("id"),
        f"{document_id}:{chunk_id}",
        limit=360,
    )
    title = _first_text(
        source.get("title"),
        _title_from_path(source.get("title_path") or source.get("titlePath")),
        chunk_id,
        limit=220,
    )
    snippet = _first_text(source.get("snippet"), source.get("text"), source.get("content"), limit=520)
    content = _first_text(source.get("content"), source.get("text"), source.get("snippet"), limit=8000)
    row: Dict[str, Any] = {
        "id": citation_id or fallback_id,
        "title": title or "文档片段",
        "source_name": _first_text(source.get("source_name"), source.get("sourceName"), "内部知识库", limit=120),
        "snippet": snippet,
        "source_type": "document",
        "citation_id": citation_id,
        "document_id": document_id,
        "chunk_id": chunk_id,
    }
    if content:
        row["content"] = content
        row["content_format"] = _first_text(source.get("content_format"), source.get("contentFormat"), "text", limit=40)
    page_no = source.get("page_no") if source.get("page_no") is not None else source.get("pageNo")
    if page_no not in (None, ""):
        row["page_no"] = page_no
    content_type = _first_text(source.get("content_type"), source.get("contentType"), limit=80)
    if content_type:
        row["content_type"] = content_type
    source_chunk_ids = source.get("source_chunk_ids") or source.get("sourceChunkIds")
    if isinstance(source_chunk_ids, list):
        row["source_chunk_ids"] = [_text(item, limit=180) for item in source_chunk_ids if _text(item)]
    source_anchor = source.get("source_anchor") or source.get("sourceAnchor")
    if isinstance(source_anchor, dict):
        row["source_anchor"] = source_anchor
    metadata = source.get("metadata")
    if isinstance(metadata, dict):
        anchor = metadata.get("sourceAnchor")
        if isinstance(anchor, dict) and "source_anchor" not in row:
            row["source_anchor"] = anchor
    return row


def _sources_from_evidence_bundle(meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    evidence_bundle = meta.get("evidenceBundle") or meta.get("evidence_bundle")
    if not isinstance(evidence_bundle, dict):
        return []
    output: List[Dict[str, Any]] = []
    for idx, source in enumerate(list(evidence_bundle.get("sources") or [])[:12], start=1):
        if isinstance(source, dict):
            row = _normalize_document_source(source, fallback_id=f"kb_doc_{idx}")
            if row:
                output.append(row)
    return output


def _sources_from_used_chunks(meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    for idx, chunk in enumerate(list(meta.get("usedChunks") or meta.get("used_chunks") or [])[:12], start=1):
        if isinstance(chunk, dict):
            row = _normalize_document_source(chunk, fallback_id=f"kb_chunk_{idx}")
            if row:
                output.append(row)
    return output


def _sources_from_citations(meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    for idx, citation in enumerate(list(meta.get("citations") or [])[:12], start=1):
        if isinstance(citation, dict):
            row = _normalize_document_source(citation, fallback_id=f"kb_citation_{idx}")
            if row:
                output.append(row)
    return output


def extract_kb_document_sources(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Project graph-time kb_search evidence rows into openable document sources.

    This function is intentionally scoped to runtime evidence projection. It does
    not change the underlying RAG/knowledge QA service payload.
    """
    if not isinstance(item, dict):
        return []
    tool = _text(item.get("tool")).lower()
    meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
    provider = _text(meta.get("provider")).lower()
    if tool not in {"kb_search", "knowledge_search"} and "knowledge" not in provider:
        return []

    candidates: List[Dict[str, Any]] = []
    direct_source = _normalize_document_source(
        {**item, **meta},
        fallback_id="kb_direct",
    )
    if direct_source:
        candidates.append(direct_source)
    candidates.extend(_sources_from_evidence_bundle(meta))
    candidates.extend(_sources_from_used_chunks(meta))
    candidates.extend(_sources_from_citations(meta))

    output: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for source in candidates:
        key = f"{source.get('document_id') or ''}:{source.get('chunk_id') or ''}"
        if not key.strip(":") or key in seen:
            continue
        seen.add(key)
        output.append(source)
    return output
