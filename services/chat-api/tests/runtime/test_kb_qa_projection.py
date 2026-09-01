from __future__ import annotations

from app.enterprise_capabilities.evidence.foundation.kb_qa_projection import sanitize_tool_results_for_evidence


def _kb_payload() -> dict:
    return {
        "ok": True,
        "mode": "qa",
        "provider": "internal_knowledge_qa",
        "query": "门店经营异常判断口径",
        "answer": "内部知识库结论：门店经营异常应同时关注目标达成率、客流环比和库存周转。",
        "usedCount": 1,
        "retrievedCount": 10,
        "usedChunks": [
            {
                "citationId": "doc-1:chunk_000001",
                "documentId": "doc-1",
                "chunkId": "chunk_000001",
                "title": "门店经营规则",
                "text": "目标达成率低于 80% 且客流环比下滑时，应进入经营异常诊断。",
                "score": 0.91,
            }
        ],
        "citations": [],
        "results": [
            {
                "title": "不应进入下游的原始候选",
                "content": "RAW_TOPN_SHOULD_NOT_BE_CONSUMED",
                "score": 0.1,
            }
        ],
    }


def test_internal_kb_qa_raw_tool_results_are_compacted() -> None:
    sanitized = sanitize_tool_results_for_evidence([{"tool": "kb_search", "result": _kb_payload()}])

    assert len(sanitized) == 1
    result = sanitized[0]["result"]
    assert result["answer"].startswith("内部知识库结论")
    assert "results" not in result
    assert result["usedChunks"][0]["chunkId"] == "chunk_000001"
