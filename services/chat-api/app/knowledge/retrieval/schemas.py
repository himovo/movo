from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RetrievalSearchPayload(BaseModel):
    query: str
    mainId: str
    knowledgeBaseId: str = ""
    topN: int = 8
    retrievalMode: str = "vector"
    rerank: Optional[bool] = None


class RetrievalChunkItem(BaseModel):
    documentId: str = ""
    chunkId: str = ""
    chunkStage: str = "rag"
    text: str = ""
    contextualText: str = ""
    titlePath: List[str] = Field(default_factory=list)
    pageNo: Optional[int] = None
    contentType: str = "text"
    sourceChunkIds: List[str] = Field(default_factory=list)
    ordinal: int = 0
    score: float = 0
    distance: Optional[float] = None
    rerankScore: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RetrievalSearchResult(BaseModel):
    query: str = ""
    retrievalMode: str = "vector"
    topN: int = 0
    items: List[RetrievalChunkItem] = Field(default_factory=list)
    total: int = 0
