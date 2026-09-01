from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional


class KnowledgeQARequest(BaseModel):
    query: str = Field(min_length=1)
    user_id: str = ""
    main_id: str = "default"
    session_id: str = ""
    knowledge_base_ids: List[str] = Field(default_factory=list)
    top_n: int = Field(default=8, ge=1, le=50)


class KnowledgeChunk(BaseModel):
    document_id: str
    chunk_id: str
    chunk_stage: str = "rag"
    text: str
    contextual_text: str = ""
    title_path: List[str] = Field(default_factory=list)
    page_no: Optional[int] = None
    content_type: str = "text"
    source_chunk_ids: List[str] = Field(default_factory=list)
    ordinal: int = 0
    score: float = 0
    rerank_score: Optional[float] = None
    distance: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeCitation(BaseModel):
    document_id: str
    chunk_id: str
    title_path: List[str] = Field(default_factory=list)
    text: str
    score: float = 0
    page_no: Optional[int] = None
    source_chunk_ids: List[str] = Field(default_factory=list)
    content_type: str = "text"
    source_anchor: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeQAResult(BaseModel):
    answer: str
    citations: List[KnowledgeCitation] = Field(default_factory=list)
    retrieved_chunks: List[KnowledgeChunk] = Field(default_factory=list)
    used_chunk_ids: List[str] = Field(default_factory=list)
    raw_model_output: str = ""
