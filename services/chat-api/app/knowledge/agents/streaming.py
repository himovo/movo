from __future__ import annotations

import json
from typing import AsyncIterator

from app.knowledge.agents.knowledge_qa_agent import knowledge_qa_agent
from app.knowledge.api.schemas import KnowledgeQARequest
from app.knowledge.citations.citation_resolver import build_evidence_bundle
async def run_knowledge_qa_runtime_stream(request: KnowledgeQARequest) -> AsyncIterator[str]:
    """Native runtime events for V3; intentionally omits legacy status prose."""

    tool_name = "kb_search"
    action_id = "knowledge_qa_retrieval"
    yield json.dumps(
        {
            "type": "tool_requested",
            "node_id": "knowledge_qa",
            "content": {
                "tool": tool_name,
                "action_id": action_id,
                "args": {"query": request.query, "knowledge_base_ids": list(request.knowledge_base_ids or [])},
            },
        },
        ensure_ascii=False,
    ) + "\n"
    chunks = await knowledge_qa_agent.retrieve_chunks(request)
    yield json.dumps(
        {
            "type": "tool_completed",
            "node_id": "knowledge_qa",
            "content": {"tool": tool_name, "action_id": action_id, "ok": True, "result_count": len(chunks)},
        },
        ensure_ascii=False,
    ) + "\n"
    result = await knowledge_qa_agent.answer_from_chunks(request, chunks)
    if result.citations:
        yield json.dumps(
            {"type": "evidence_bundle", "node_id": "knowledge_qa", "content": build_evidence_bundle(request.query, result.citations)},
            ensure_ascii=False,
        ) + "\n"
    if result.answer:
        yield json.dumps({"type": "answer", "content": result.answer}, ensure_ascii=False) + "\n"
