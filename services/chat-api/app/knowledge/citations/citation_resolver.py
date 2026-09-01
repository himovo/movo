from __future__ import annotations

import json
import re
from typing import Any

from app.knowledge.api.schemas import KnowledgeChunk, KnowledgeCitation


def parse_llm_json(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {"answer": "", "usedChunkIds": []}
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {"answer": text, "usedChunkIds": []}
    except Exception:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if match:
            try:
                parsed = json.loads(match.group(0))
                return parsed if isinstance(parsed, dict) else {"answer": text, "usedChunkIds": []}
            except Exception:
                pass
    return {"answer": text, "usedChunkIds": []}


def _source_anchor(chunk: KnowledgeChunk) -> dict[str, Any]:
    anchor: dict[str, Any] = {
        "documentId": chunk.document_id,
        "chunkId": chunk.chunk_id,
        "chunkStage": chunk.chunk_stage,
        "pageNo": chunk.page_no,
        "sourceChunkIds": chunk.source_chunk_ids,
    }
    metadata = chunk.metadata or {}
    for key in ("sourceAnchor", "anchor", "bbox", "boundingBox", "pageBbox"):
        value = metadata.get(key)
        if value:
            anchor[key] = value
    return {key: value for key, value in anchor.items() if value not in (None, "", [])}


def _citation_from_chunk(chunk: KnowledgeChunk) -> KnowledgeCitation:
    return KnowledgeCitation(
        document_id=chunk.document_id,
        chunk_id=chunk.chunk_id,
        title_path=chunk.title_path,
        text=chunk.contextual_text or chunk.text,
        score=chunk.score,
        page_no=chunk.page_no,
        source_chunk_ids=chunk.source_chunk_ids,
        content_type=chunk.content_type,
        source_anchor=_source_anchor(chunk),
    )


def resolve_citations(chunks: list[KnowledgeChunk], used_chunk_ids: list[str]) -> list[KnowledgeCitation]:
    by_citation_id = {f"{chunk.document_id}:{chunk.chunk_id}": chunk for chunk in chunks}
    by_chunk_id: dict[str, KnowledgeChunk] = {}
    duplicate_chunk_ids: set[str] = set()
    for chunk in chunks:
        if chunk.chunk_id in by_chunk_id:
            duplicate_chunk_ids.add(chunk.chunk_id)
            continue
        by_chunk_id[chunk.chunk_id] = chunk
    output: list[KnowledgeCitation] = []
    seen: set[str] = set()
    requested_any = False
    for chunk_id in used_chunk_ids:
        key = str(chunk_id or "").strip()
        if not key:
            continue
        requested_any = True
        if key in seen:
            continue
        chunk = by_citation_id.get(key)
        if chunk is None and key not in duplicate_chunk_ids:
            chunk = by_chunk_id.get(key)
        if chunk is None:
            continue
        seen.add(key)
        output.append(_citation_from_chunk(chunk))
    if not output and not requested_any and chunks:
        chunk = chunks[0]
        output.append(_citation_from_chunk(chunk))
    return output


def build_evidence_bundle(query: str, citations: list[KnowledgeCitation]) -> dict[str, Any]:
    sources = []
    for item in citations:
        title = " / ".join(item.title_path) or item.chunk_id
        citation_id = f"{item.document_id}:{item.chunk_id}"
        sources.append(
            {
                "id": citation_id,
                "citation_id": citation_id,
                "title": title,
                "source_name": "内部知识库",
                "snippet": item.text[:500],
                "content": item.text,
                "source_type": "document",
                "content_format": "text",
                "document_id": item.document_id,
                "chunk_id": item.chunk_id,
                "page_no": item.page_no,
                "content_type": item.content_type,
                "source_chunk_ids": item.source_chunk_ids,
                "source_anchor": item.source_anchor,
            }
        )
    return {
        "summary": f"内部知识问答检索到 {len(citations)} 条引用来源",
        "sources": sources,
        "confirmed_facts": [f"问题：{query}"],
        "open_questions": [],
    }
