"""Canonical EvidenceBundle adapters for non-search enterprise capabilities."""

from __future__ import annotations

from typing import Any

from app.enterprise_capabilities.evidence.foundation import EvidenceNormalizer, build_user_evidence_payload
from app.enterprise_capabilities.evidence.foundation.kb_qa_projection import sanitize_tool_results_for_evidence


def _bundle(
    *,
    tool_name: str,
    query: str,
    results: list[dict[str, Any]],
    raw_summary: dict[str, Any],
) -> dict[str, Any]:
    if not results:
        return {}
    return EvidenceNormalizer.build_research_bundle(
        query=query,
        tools_used=[tool_name],
        results=results,
        raw_tool_results=sanitize_tool_results_for_evidence([
            {"tool": tool_name, "result": raw_summary}
        ]),
    )


def build_knowledge_evidence_bundle(
    *,
    query: str,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for index, item in enumerate(items[:20], start=1):
        if not isinstance(item, dict):
            continue
        content = str(item.get("contextualText") or item.get("text") or "").strip()
        if not content:
            continue
        metadata = dict(item.get("metadata") or {})
        title_path = [str(value).strip() for value in list(item.get("titlePath") or []) if str(value).strip()]
        title = str(
            metadata.get("document_title")
            or metadata.get("filename")
            or metadata.get("title")
            or (" / ".join(title_path) if title_path else "")
            or f"内部知识来源 {index}"
        ).strip()
        results.append({
            "tool": "knowledge_search",
            "title": title,
            "source": "MOVO internal knowledge",
            "content": content,
            "summary": content,
            "score": item.get("rerankScore") if item.get("rerankScore") is not None else item.get("score"),
            "meta": {
                "document_id": str(item.get("documentId") or ""),
                "chunk_id": str(item.get("chunkId") or ""),
                "page_no": item.get("pageNo"),
                "title_path": title_path,
                "provenance": "knowledge_retrieval",
            },
        })
    return _bundle(
        tool_name="knowledge_search",
        query=query,
        results=results,
        raw_summary={"query": query, "total": len(results)},
    )


def build_document_evidence_bundle(
    *,
    purpose: str,
    parse_result: dict[str, Any],
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for index, item in enumerate(list(parse_result.get("parsed_documents") or [])[:12], start=1):
        if not isinstance(item, dict) or str(item.get("parse_status") or "") != "parsed":
            continue
        markdown = str(item.get("markdown") or "").strip()
        if not markdown:
            continue
        profile = dict(item.get("profile") or {})
        summary = str(
            profile.get("active_context_brief")
            or profile.get("summary")
            or item.get("inline_markdown")
            or markdown
        ).strip()
        filename = str(item.get("filename") or f"document_{index}").strip()
        results.append({
            "tool": "document_parse",
            "title": filename,
            "source": filename,
            "content": markdown,
            "summary": summary,
            "meta": {
                "object_path": str(item.get("object_path") or ""),
                "content_type": str(item.get("content_type") or ""),
                "parse_quality": dict(item.get("parse_quality") or {}),
                "provenance": "authenticated_document_parse",
            },
        })
    return _bundle(
        tool_name="document_parse",
        query=purpose,
        results=results,
        raw_summary={
            "purpose": purpose,
            "documents": [
                {
                    "title": item["title"],
                    "object_path": str((item.get("meta") or {}).get("object_path") or ""),
                }
                for item in results
            ],
        },
    )


def public_capability_evidence(bundle: dict[str, Any]) -> dict[str, Any]:
    return build_user_evidence_payload(bundle) if bundle else {}


__all__ = [
    "build_document_evidence_bundle",
    "build_knowledge_evidence_bundle",
    "public_capability_evidence",
]
