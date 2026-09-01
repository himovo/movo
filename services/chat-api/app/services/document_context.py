from __future__ import annotations

import json
import math
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from app.llm.factory import get_request_scoped_llm_client
from app.llm.types import Message, Role


class ChunkSemanticBrief(BaseModel):
    summary: str = ""
    key_points: List[str] = Field(default_factory=list)
    section_signals: List[str] = Field(default_factory=list)
    subject_candidates: List[str] = Field(default_factory=list)


class DocumentSemanticProfile(BaseModel):
    title: str = ""
    summary: str = ""
    content_type_hint: str = ""
    key_points: List[str] = Field(default_factory=list)
    section_outline: List[str] = Field(default_factory=list)
    subject_candidates: List[str] = Field(default_factory=list)
    active_context_brief: str = ""


class DocumentContextService:
    INLINE_MARKDOWN_LIMIT = 80000
    CHUNK_CHARS = 5000
    MAX_CHUNKS = 8

    def __init__(self) -> None:
        self._llm = None

    def _planner_llm(self):
        if self._llm is None:
            self._llm = get_request_scoped_llm_client(streaming=False, stage="planning")
        return self._llm

    @staticmethod
    def _split_markdown(markdown: str, *, chunk_chars: int, max_chunks: int) -> List[str]:
        text = str(markdown or "").strip()
        if not text:
            return []
        if len(text) <= chunk_chars:
            return [text]

        paragraphs = [block.strip() for block in text.split("\n\n") if block.strip()]
        chunks: List[str] = []
        current: List[str] = []
        current_len = 0
        for para in paragraphs:
            para_len = len(para) + (2 if current else 0)
            if current and current_len + para_len > chunk_chars:
                chunks.append("\n\n".join(current).strip())
                current = [para]
                current_len = len(para)
            else:
                current.append(para)
                current_len += para_len
        if current:
            chunks.append("\n\n".join(current).strip())
        if len(chunks) <= max_chunks:
            return chunks

        selected: List[str] = []
        total = len(chunks)
        for idx in range(max_chunks):
            pos = 0 if max_chunks == 1 else round(idx * (total - 1) / (max_chunks - 1))
            token = chunks[min(max(pos, 0), total - 1)]
            if token not in selected:
                selected.append(token)
        return selected[:max_chunks]

    async def _summarize_chunk(
        self,
        *,
        chunk: str,
        filename: str,
        user_text: str,
        chunk_index: int,
        chunk_total: int,
    ) -> ChunkSemanticBrief:
        system = (
            "You analyze a markdown chunk from an uploaded document for downstream task execution.\n"
            "Return strict JSON with fields:\n"
            "- summary\n"
            "- key_points[]\n"
            "- section_signals[]\n"
            "- subject_candidates[]\n"
            "Requirements:\n"
            "- Summarize only the chunk's actual content.\n"
            "- Prefer semantic understanding over copying raw lines.\n"
            "- Keep key_points concise and factual.\n"
            "- section_signals should name the main section/topic shown in this chunk.\n"
            "- subject_candidates should capture the most likely subject or document focus.\n"
        )
        payload = {
            "filename": filename,
            "user_request": str(user_text or "")[:1200],
            "chunk_index": chunk_index,
            "chunk_total": chunk_total,
            "markdown_chunk": str(chunk or "")[:8000],
        }
        try:
            model = self._planner_llm().with_structured_output(ChunkSemanticBrief, method="function_calling")
            parsed = await model.ainvoke(
                [
                    Message(role=Role.SYSTEM, content=system),
                    Message(role=Role.USER, content=json.dumps(payload, ensure_ascii=False)),
                ]
            )
            if isinstance(parsed, ChunkSemanticBrief):
                return parsed
        except Exception:
            pass
        fallback_summary = str(chunk or "").strip()[:600]
        return ChunkSemanticBrief(summary=fallback_summary, key_points=[fallback_summary] if fallback_summary else [])

    async def _build_profile(
        self,
        *,
        filename: str,
        user_text: str,
        markdown: str,
        chunk_briefs: List[ChunkSemanticBrief],
    ) -> DocumentSemanticProfile:
        payload = {
            "filename": filename,
            "user_request": str(user_text or "")[:1200],
            "chunk_briefs": [brief.model_dump() for brief in chunk_briefs],
            "markdown_preview": str(markdown or "")[:3000],
        }
        system = (
            "You build a compact semantic profile for an uploaded document.\n"
            "Return strict JSON with fields:\n"
            "- title\n"
            "- summary\n"
            "- content_type_hint\n"
            "- key_points[]\n"
            "- section_outline[]\n"
            "- subject_candidates[]\n"
            "- active_context_brief\n"
            "Requirements:\n"
            "- active_context_brief should help a downstream writer or file-transformer use the document correctly.\n"
            "- Keep the profile compact, grounded, and task-oriented.\n"
            "- Do not invent requirements not supported by the document.\n"
        )
        try:
            model = self._planner_llm().with_structured_output(DocumentSemanticProfile, method="function_calling")
            parsed = await model.ainvoke(
                [
                    Message(role=Role.SYSTEM, content=system),
                    Message(role=Role.USER, content=json.dumps(payload, ensure_ascii=False)),
                ]
            )
            if isinstance(parsed, DocumentSemanticProfile):
                return parsed
        except Exception:
            pass

        summaries = [str(item.summary or "").strip() for item in chunk_briefs if str(item.summary or "").strip()]
        points: List[str] = []
        for item in chunk_briefs:
            for point in list(item.key_points or []):
                token = str(point or "").strip()
                if token and token not in points:
                    points.append(token)
        return DocumentSemanticProfile(
            title=filename,
            summary=summaries[0] if summaries else str(markdown or "")[:500],
            content_type_hint="document",
            key_points=points[:6],
            section_outline=[],
            subject_candidates=[],
            active_context_brief=summaries[0] if summaries else str(markdown or "")[:500],
        )

    async def build_context(
        self,
        *,
        markdown: str,
        filename: str,
        user_text: str,
    ) -> Dict[str, Any]:
        text = str(markdown or "").strip()
        if not text:
            return {
                "profile": {},
                "inline_markdown": "",
                "inline_mode": "empty",
                "chunk_briefs": [],
            }

        chunks = self._split_markdown(
            text,
            chunk_chars=self.CHUNK_CHARS,
            max_chunks=self.MAX_CHUNKS,
        )
        briefs: List[ChunkSemanticBrief] = []
        total = len(chunks)
        for idx, chunk in enumerate(chunks, start=1):
            briefs.append(
                await self._summarize_chunk(
                    chunk=chunk,
                    filename=filename,
                    user_text=user_text,
                    chunk_index=idx,
                    chunk_total=total,
                )
            )
        profile = await self._build_profile(
            filename=filename,
            user_text=user_text,
            markdown=text,
            chunk_briefs=briefs,
        )
        inline_markdown = text if len(text) <= self.INLINE_MARKDOWN_LIMIT else ""
        inline_mode = "full" if inline_markdown else "summary_only"
        return {
            "profile": profile.model_dump(),
            "inline_markdown": inline_markdown,
            "inline_mode": inline_mode,
            "chunk_briefs": [brief.model_dump() for brief in briefs],
            "markdown_chars": len(text),
            "chunk_count": total,
            "sampled_ratio": round(min(1.0, total / max(math.ceil(len(text) / self.CHUNK_CHARS), 1)), 3),
        }


document_context_service = DocumentContextService()
