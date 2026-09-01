from __future__ import annotations

import asyncio

from app.enterprise_capabilities.presentation.evidence import presentation_tool_observations
from app.enterprise_capabilities.runtime import CapabilityExecutionContext
from app.enterprise_capabilities.runtime import adapters
from app.knowledge.retrieval.schemas import RetrievalChunkItem, RetrievalSearchResult


def _context(**turn_context) -> CapabilityExecutionContext:
    return CapabilityExecutionContext(
        tenant_id="tenant-a",
        user_id="user-a",
        conversation_id="conversation-a",
        kernel_session_id="session-a",
        profile_version="profile-a",
        action_id="action-a",
        message_id="message-a",
        model_instance_id="model-a",
        turn_context=turn_context,
    )


def test_knowledge_search_produces_execution_evidence_only_when_items_exist(monkeypatch) -> None:
    async def search(**kwargs):
        return RetrievalSearchResult(
            query=kwargs["query"],
            retrievalMode="vector",
            total=1,
            items=[RetrievalChunkItem(
                documentId="doc-a",
                chunkId="chunk-a",
                text="AskBot supports enterprise knowledge retrieval.",
                titlePath=["AskBot product guide", "Knowledge"],
                pageNo=3,
                score=0.92,
            )],
        )

    monkeypatch.setattr(adapters.knowledge_retrieval_client, "search", search)
    result = asyncio.run(adapters.knowledge_search(
        {"query": "AskBot knowledge"},
        _context(knowledge_base_ids=["kb-a"]),
    ))

    bundle = result["_execution_evidence_bundle"]
    assert bundle["tools_used"] == ["knowledge_search"]
    assert bundle["results"][0]["title"] == "AskBot product guide / Knowledge"
    assert bundle["results"][0]["content"].startswith("AskBot supports")
    assert bundle["results"][0]["meta"]["document_id"] == "doc-a"
    # Knowledge chunks are presented as openable document sources while their
    # source_name still identifies the internal knowledge repository.
    assert result["evidence_bundle"]["sources"][0]["source_type"] == "document"

    async def empty(**kwargs):
        return RetrievalSearchResult(query=kwargs["query"], items=[], total=0)

    monkeypatch.setattr(adapters.knowledge_retrieval_client, "search", empty)
    empty_result = asyncio.run(adapters.knowledge_search(
        {"query": "missing"}, _context(),
    ))
    assert "_execution_evidence_bundle" not in empty_result


def test_knowledge_search_keeps_agent_candidates_but_projects_only_admitted_evidence(monkeypatch) -> None:
    async def search(**kwargs):
        return RetrievalSearchResult(
            query=kwargs["query"],
            retrievalMode="vector",
            total=2,
            items=[
                RetrievalChunkItem(
                    documentId="token-report",
                    chunkId="token-1",
                    text="Token 是智能服务的计量和定价单位。",
                    titlePath=["Token 经济报告"],
                    score=0.7176740400350329,
                ),
                RetrievalChunkItem(
                    documentId="movo-acceptance",
                    chunkId="acceptance-1",
                    text="星轨计划文档化验收资料。",
                    titlePath=["MOVO 文档化验收资料"],
                    score=0.005949579483329656,
                ),
            ],
        )

    monkeypatch.setattr(adapters.knowledge_retrieval_client, "search", search)
    result = asyncio.run(adapters.knowledge_search(
        {"query": "Token 经济是什么"},
        _context(),
    ))

    assert len(result["items"]) == 2
    assert result["retrieved_total"] == 2
    assert result["evidence_total"] == 1
    assert result["evidence_available"] is True
    assert len(result["_execution_evidence_bundle"]["results"]) == 1
    assert result["_execution_evidence_bundle"]["results"][0]["title"] == "Token 经济报告"
    assert [source["title"] for source in result["evidence_bundle"]["sources"]] == ["Token 经济报告"]


def test_document_parse_produces_bounded_authenticated_document_evidence(monkeypatch) -> None:
    async def parse_documents(**kwargs):
        return {
            "parsed_documents": [{
                "asset_id": "runtime_document_1",
                "filename": "AskBot介绍.pdf",
                "object_path": "user-a/2026/08/askbot.pdf",
                "content_type": "application/pdf",
                "parse_status": "parsed",
                "markdown": "# AskBot\n企业智能体平台，支持知识搜索和业务自动化。",
                "profile": {"summary": "AskBot 企业智能体平台产品介绍。"},
                "parse_quality": {"score": 0.99},
                "embedded_images": [],
            }],
            "active_document_markdown": "# AskBot",
        }

    monkeypatch.setattr(adapters.runtime_parse_service, "parse_documents", parse_documents)
    result = asyncio.run(adapters.document_parse(
        {
            "purpose": "根据附件制作PPT",
            "artifacts": [{
                "object_path": "user-a/2026/08/askbot.pdf",
                "filename": "AskBot介绍.pdf",
            }],
        },
        _context(),
    ))

    bundle = result["_execution_evidence_bundle"]
    evidence = bundle["results"][0]
    assert bundle["tools_used"] == ["document_parse"]
    assert evidence["title"] == "AskBot介绍.pdf"
    assert evidence["summary"] == "AskBot 企业智能体平台产品介绍。"
    assert evidence["content"].startswith("# AskBot")
    assert evidence["meta"]["object_path"] == "user-a/2026/08/askbot.pdf"
    assert result["evidence_bundle"]["sources"][0]["source_type"] == "document"


def test_presentation_observations_accept_merged_search_knowledge_and_document_evidence() -> None:
    observations = presentation_tool_observations({
        "evidence_bundle": {
            "results": [
                {
                    "tool": "external_search", "title": "AskBot 官网",
                    "content": "公开产品定位。", "source_url": "https://askbot.cn",
                },
                {
                    "tool": "knowledge_search", "title": "内部产品手册",
                    "content": "内部功能说明。", "source": "ASKAI internal knowledge",
                },
                {
                    "tool": "document_parse", "title": "方案.pdf",
                    "content": "附件实施方案。", "source": "方案.pdf",
                },
            ],
        }
    })

    assert [item["tool"] for item in observations] == [
        "external_search", "knowledge_search", "document_parse",
    ]
    assert [item["source_label"] for item in observations] == [
        "AskBot 官网", "内部产品手册", "方案.pdf",
    ]


def test_presentation_observations_are_empty_without_upstream_evidence() -> None:
    assert presentation_tool_observations({}) == []
