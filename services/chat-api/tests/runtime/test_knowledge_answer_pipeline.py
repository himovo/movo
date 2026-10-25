import asyncio
import json

from app.knowledge.api.schemas import KnowledgeChunk, KnowledgeQARequest
from app.knowledge.agents import knowledge_qa_agent as qa_module


def _chunk(text: str) -> KnowledgeChunk:
    return KnowledgeChunk(
        document_id="document-1", chunk_id="chunk_000001", text=text,
        metadata={"document_title": "手册"},
    )


def test_pipeline_preserves_model_answer_with_valid_citation(monkeypatch):
    class FakeLLM:
        def __init__(self, *, intent):
            assert intent == "knowledge_qa"

        async def chat_complete(self, _messages, temperature=None):
            return json.dumps({
                "answer": "默认 25%，最小 10%，最大 30%。",
                "usedChunkIds": ["document-1:chunk_000001"],
            })

    monkeypatch.setattr(qa_module, "LLMService", FakeLLM)
    request = KnowledgeQARequest(query="低液位阈值是多少？", main_id="tenant")
    result = asyncio.run(qa_module.KnowledgeQAAgent().answer_from_chunks(
        request, [_chunk("デフォルトは25％、最小は10％、最大は30％。")],
    ))
    assert result.answer == "默认 25%，最小 10%，最大 30%。"
    assert result.used_chunk_ids == ["document-1:chunk_000001"]


def test_pipeline_preserves_generated_text_when_citation_resolves(monkeypatch):
    class FakeLLM:
        def __init__(self, *, intent):
            assert intent == "knowledge_qa"

        async def chat_complete(self, _messages, temperature=None):
            return json.dumps({
                "answer": "每年 3 月、9 月集中申请。\n由人事部汇总。",
                "usedChunkIds": ["document-1:chunk_000001"],
            })

    monkeypatch.setattr(qa_module, "LLMService", FakeLLM)
    request = KnowledgeQARequest(query="工装每年何时集中申请？", main_id="tenant")
    result = asyncio.run(qa_module.KnowledgeQAAgent().answer_from_chunks(
        request, [_chunk("公司每年 3 月、9 月集中申请工装，由人事部汇总。")],
    ))
    assert result.answer == "每年 3 月、9 月集中申请。\n由人事部汇总。"


def test_pipeline_rejects_answer_without_resolvable_citation(monkeypatch):
    class FakeLLM:
        def __init__(self, *, intent):
            pass

        async def chat_complete(self, _messages, temperature=None):
            return json.dumps({
                "answer": "期限是 3 天。",
                "usedChunkIds": ["missing:chunk_1"],
            })

    monkeypatch.setattr(qa_module, "LLMService", FakeLLM)
    request = KnowledgeQARequest(query="期限多久？", main_id="tenant")
    result = asyncio.run(qa_module.KnowledgeQAAgent().answer_from_chunks(
        request, [_chunk("期限是 3 天。")],
    ))
    assert result.answer == "内部知识库中未找到足够依据。"
    assert not result.citations
