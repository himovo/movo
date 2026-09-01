from __future__ import annotations

from app.enterprise_capabilities.evidence.capability_bundles import (
    build_knowledge_evidence_bundle,
    public_capability_evidence,
)
from app.dsh_runtime.evidence_projection import (
    build_execution_evidence_event,
    project_execution_evidence,
)


def test_knowledge_search_evidence_preserves_document_locator() -> None:
    bundle = build_knowledge_evidence_bundle(
        query="Token 经济是什么？",
        items=[
            {
                "documentId": "document-1",
                "chunkId": "chunk-7",
                "contextualText": "Token 是可计量的智能计价单位。",
                "titlePath": ["Token 经济", "结论"],
                "pageNo": 6,
                "contentType": "text",
            }
        ],
    )

    payload = public_capability_evidence(bundle)

    assert len(payload["sources"]) == 1
    source = payload["sources"][0]
    assert source["source_type"] == "document"
    assert source["document_id"] == "document-1"
    assert source["chunk_id"] == "chunk-7"
    assert source["page_no"] == 6
    assert source["title"] == "Token 经济 / 结论"


def test_execution_evidence_projection_returns_openable_sources() -> None:
    execution_bundle = build_knowledge_evidence_bundle(
        query="Token 经济是什么？",
        items=[
            {
                "documentId": "document-1",
                "chunkId": "chunk-7",
                "contextualText": "Token 是可计量的智能计价单位。",
                "titlePath": ["Token 经济", "结论"],
                "pageNo": 6,
            }
        ],
    )

    payload = project_execution_evidence(
        execution_bundle,
        evidence_id="evidence-message-1",
    )

    assert payload["id"] == "evidence-message-1"
    assert payload["sources"][0]["document_id"] == "document-1"
    assert payload["sources"][0]["chunk_id"] == "chunk-7"

    event = build_execution_evidence_event(message_id="message-1", payload=payload)
    assert event["type"] == "item.completed"
    assert event["item_kind"] == "evidence"
    assert event["item_id"] == "evidence-message-1"
    assert event["payload"]["sources"][0]["chunk_id"] == "chunk-7"
