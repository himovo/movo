from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


JobStatus = Literal["queued", "running", "succeeded", "failed"]


class StorageRef(BaseModel):
    storageType: Literal["local", "oss"] = "local"
    storageBucket: str = ""
    storageKey: str = Field(min_length=1)
    filename: str = ""
    mimeType: str = ""


class CallbackRef(BaseModel):
    url: str = Field(min_length=1)
    token: str = Field(min_length=1)


class PreviewConvertJobRequest(BaseModel):
    documentId: str = Field(min_length=1)
    mainId: str = "default"
    source: StorageRef
    target: StorageRef
    callback: CallbackRef


class ArtifactTarget(BaseModel):
    storageType: Literal["local", "oss"] = "local"
    storageBucket: str = ""
    storagePrefix: str = Field(min_length=1)


class ParseDocumentJobRequest(BaseModel):
    documentId: str = Field(min_length=1)
    mainId: str = "default"
    source: StorageRef
    artifacts: ArtifactTarget
    callback: CallbackRef
    minChunkSize: int = Field(default=800, ge=50, le=4000)
    chunkSize: int = Field(default=1500, ge=200, le=8000)
    chunkOverlap: int = Field(default=80, ge=0, le=2000)


class ParseMarkdownRequest(BaseModel):
    source: StorageRef
    sourceUrl: str = ""
    minChunkSize: int = Field(default=800, ge=50, le=4000)
    chunkSize: int = Field(default=1500, ge=200, le=8000)
    chunkOverlap: int = Field(default=80, ge=0, le=2000)


class ParseMarkdownResponse(BaseModel):
    markdown: str
    raw: dict = Field(default_factory=dict)
    rawChunks: list[dict] = Field(default_factory=list)
    ragChunks: list[dict] = Field(default_factory=list)
    parser: str = ""
    markdownChars: int = 0


class IndexDocumentJobRequest(BaseModel):
    documentId: str = Field(min_length=1)
    mainId: str = "default"
    knowledgeBaseId: str = ""
    chunkStage: Literal["rag", "raw"] = "rag"
    config: dict = Field(default_factory=dict)
    callback: CallbackRef


class DeleteDocumentVectorsRequest(BaseModel):
    documentId: str = Field(min_length=1)
    mainId: str = "default"
    config: dict = Field(default_factory=dict)


class RetrievalSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    mainId: str = "default"
    knowledgeBaseId: str = ""
    topN: int | None = Field(default=None, ge=1, le=100)
    candidateTopK: int | None = Field(default=None, ge=1, le=500)
    retrievalMode: Literal["vector", "hybrid"] | None = None
    filters: dict = Field(default_factory=dict)
    rerank: bool | None = None


class PreviewConvertJobResponse(BaseModel):
    jobId: str
    status: JobStatus


class ParseDocumentJobResponse(BaseModel):
    jobId: str
    status: JobStatus


class IndexDocumentJobResponse(BaseModel):
    jobId: str
    status: JobStatus
