from __future__ import annotations

import re

from app.knowledge.api.schemas import KnowledgeChunk, KnowledgeQARequest, KnowledgeQAResult
from app.knowledge.citations.citation_resolver import parse_llm_json, resolve_citations
from app.knowledge.prompting.knowledge_qa_prompt import build_knowledge_qa_messages
from app.knowledge.retrieval.retrieval_client import knowledge_retrieval_client
from app.services.llm import LLMService


_USED_CHUNK_IDS_RE = re.compile(
    r",?\s*[\"']?usedChunkIds[\"']?\s*:\s*\[[^\]]*]\s*}?\s*$",
    re.I | re.S,
)


def _clean_answer_text(value: str) -> str:
    text = str(value or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json|markdown)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    text = _USED_CHUNK_IDS_RE.sub("", text).strip()
    text = re.sub(r"\s*}\s*$", "", text).strip()
    return text


def _extract_used_chunk_ids(raw: str) -> list[str]:
    text = str(raw or "")
    match = re.search(r"[\"']?usedChunkIds[\"']?\s*:\s*\[([^\]]*)]", text, flags=re.I | re.S)
    if not match:
        return []
    return re.findall(r"(?:[0-9a-f]{24,64}:)?chunk_[0-9A-Za-z_-]+", match.group(1), flags=re.I)


class KnowledgeQAAgent:
    async def retrieve_chunks(self, request: KnowledgeQARequest) -> list[KnowledgeChunk]:
        retrieval = await knowledge_retrieval_client.search(
            query=request.query,
            main_id=request.main_id,
            knowledge_base_ids=request.knowledge_base_ids,
            top_n=request.top_n,
            rerank=None,
        )
        return [
            KnowledgeChunk(
                document_id=item.documentId,
                chunk_id=item.chunkId,
                chunk_stage=item.chunkStage,
                text=item.text,
                contextual_text=item.contextualText,
                title_path=item.titlePath,
                page_no=item.pageNo,
                content_type=item.contentType,
                source_chunk_ids=item.sourceChunkIds,
                ordinal=item.ordinal,
                score=float(item.rerankScore if item.rerankScore is not None else item.score or 0),
                rerank_score=float(item.rerankScore) if item.rerankScore is not None else None,
                distance=item.distance,
                metadata=item.metadata,
            )
            for item in retrieval.items
            if item.text.strip() or item.contextualText.strip()
        ]

    async def answer_from_chunks(self, request: KnowledgeQARequest, chunks: list[KnowledgeChunk]) -> KnowledgeQAResult:
        if not chunks:
            return KnowledgeQAResult(
                answer="未在内部知识库中找到相关内容。",
                citations=[],
                retrieved_chunks=[],
                used_chunk_ids=[],
            )

        messages = build_knowledge_qa_messages(request.query, chunks)
        raw = await LLMService(intent="knowledge_qa").chat_complete(messages, temperature=None)
        parsed = parse_llm_json(raw)
        answer = _clean_answer_text(str(parsed.get("answer") or "")) or "内部知识库中未找到足够依据。"
        raw_used = parsed.get("usedChunkIds") or parsed.get("used_chunk_ids") or []
        if isinstance(raw_used, str):
            used_chunk_ids = [raw_used]
        elif isinstance(raw_used, list):
            used_chunk_ids = [str(item) for item in raw_used]
        else:
            used_chunk_ids = []
        if not used_chunk_ids:
            used_chunk_ids = _extract_used_chunk_ids(raw)
        citations = resolve_citations(chunks, used_chunk_ids)
        return KnowledgeQAResult(
            answer=answer,
            citations=citations,
            retrieved_chunks=chunks,
            used_chunk_ids=[f"{item.document_id}:{item.chunk_id}" for item in citations],
            raw_model_output=raw,
        )

    async def answer(self, request: KnowledgeQARequest) -> KnowledgeQAResult:
        chunks = await self.retrieve_chunks(request)
        return await self.answer_from_chunks(request, chunks)


knowledge_qa_agent = KnowledgeQAAgent()
