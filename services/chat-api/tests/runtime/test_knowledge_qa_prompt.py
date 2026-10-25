from app.knowledge.api.schemas import KnowledgeChunk
from app.knowledge.prompting.knowledge_qa_prompt import build_knowledge_qa_messages
from app.knowledge.citations.citation_resolver import resolve_citations


def test_knowledge_qa_prompt_enforces_evidence_boundary() -> None:
    messages = build_knowledge_qa_messages(
        "这个异常怎么处理？",
        [
            KnowledgeChunk(
                document_id="doc-1",
                chunk_id="chunk_000001",
                text="异常 A 的处理方式是重新扫码。",
                title_path=["异常处理手册"],
                score=0.91,
            )
        ],
    )

    system = messages[0]["content"]
    assert "answer 只能使用内部知识候选 content 中明确出现的信息" in system
    assert "一律不得写入 answer" in system
    assert "不要用常识、行业经验、流程经验或你自己的推断补全信息" in system
    assert "不得新增候选片段未支持的处理建议" in system
    assert "只回答用户实际询问的事实与必要适用条件" in system
    assert "不得移用该建议" in system
    assert "usedChunkIds" in system
    assert "supportChecks" not in system


def test_knowledge_qa_prompt_keeps_candidate_citation_and_content() -> None:
    messages = build_knowledge_qa_messages(
        "这个异常怎么处理？",
        [
            KnowledgeChunk(
                document_id="doc-1",
                chunk_id="chunk_000001",
                text="异常 A 的处理方式是重新扫码。",
                contextual_text="异常 A 出现时，处理方式是重新扫码。",
                title_path=["异常处理手册"],
                score=0.91,
            )
        ],
    )

    user = messages[1]["content"]
    assert "citationId: doc-1:chunk_000001" in user
    assert "异常 A 出现时，处理方式是重新扫码。" in user
    assert "请基于上述候选回答，并在 usedChunkIds 中列出实际使用的 chunkId" in user


def test_missing_used_chunk_ids_do_not_fabricate_first_candidate_as_evidence() -> None:
    chunks = [
        KnowledgeChunk(
            document_id="candidate-only",
            chunk_id="chunk_000001",
            text="这是召回候选，但模型没有声明实际使用。",
            score=0.9,
        )
    ]

    assert resolve_citations(chunks, []) == []
