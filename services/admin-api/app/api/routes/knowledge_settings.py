from __future__ import annotations

import os
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Literal

from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from app.api.deps import get_current_admin_user
from app.api.time_utils import utc_iso
from app.core.db import get_db
from app.repositories.model_repository import encrypt_secret, find_instance_by_id, mask_secret

router = APIRouter()

COLLECTION = "knowledge_document_settings"


def _default_vector_endpoint() -> str:
    return (
        os.getenv("ASKAI_ADMIN_KNOWLEDGE_WEAVIATE_ENDPOINT", "")
        or os.getenv("MOVO_DOC_PROCESSING_WEAVIATE_ENDPOINT", "")
        or "http://127.0.0.1:8080"
    )


def _default_vector_collection_name() -> str:
    return (
        os.getenv("ASKAI_ADMIN_KNOWLEDGE_WEAVIATE_COLLECTION_NAME", "")
        or os.getenv("MOVO_DOC_PROCESSING_WEAVIATE_COLLECTION_NAME", "")
        or "AskAIKnowledgeChunks"
    )


def _default_vector_distance_metric() -> str:
    value = (
        os.getenv("ASKAI_ADMIN_KNOWLEDGE_WEAVIATE_DISTANCE_METRIC", "")
        or os.getenv("MOVO_DOC_PROCESSING_WEAVIATE_DISTANCE_METRIC", "")
        or "cosine"
    )
    return value if value in {"cosine", "dot", "l2"} else "cosine"


def _default_int_env(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, "") or default)
    except ValueError:
        return default


def _default_min_chunk_size() -> int:
    return _default_int_env("ASKAI_ADMIN_KNOWLEDGE_MIN_CHUNK_SIZE", 800)


def _default_max_chunk_size() -> int:
    return _default_int_env("ASKAI_ADMIN_KNOWLEDGE_CHUNK_SIZE", 1500)


def _default_chunk_overlap() -> int:
    return _default_int_env("ASKAI_ADMIN_KNOWLEDGE_CHUNK_OVERLAP", 120)


class KnowledgeParseSettingsPayload(BaseModel):
    minChunkSize: int = Field(default_factory=_default_min_chunk_size, ge=50, le=4000)
    maxChunkSize: int = Field(default_factory=_default_max_chunk_size, ge=200, le=8000)
    chunkOverlap: int = Field(default_factory=_default_chunk_overlap, ge=0, le=2000)


class EmbeddingSettingsPayload(BaseModel):
    provider: Literal["model_center"] = "model_center"
    modelInstanceId: str = Field(default="", max_length=120)
    dimension: int = Field(default=1536, ge=1, le=20000)
    batchSize: int = Field(default=32, ge=1, le=256)
    timeoutSeconds: int = Field(default=30, ge=1, le=300)


class VectorStoreSettingsPayload(BaseModel):
    type: Literal["weaviate", "qdrant", "milvus", "elasticsearch", "opensearch", "pgvector"] = "weaviate"
    endpoint: str = Field(default_factory=_default_vector_endpoint, max_length=500)
    apiKey: str = Field(default="", max_length=1200)
    collectionName: str = Field(default_factory=_default_vector_collection_name, min_length=1, max_length=120)
    distanceMetric: Literal["cosine", "dot", "l2"] = Field(default_factory=_default_vector_distance_metric)
    tenantIsolation: bool = True
    recreateIndexAllowed: bool = False


class HybridSettingsPayload(BaseModel):
    vectorWeight: float = Field(default=0.7, ge=0, le=1)
    keywordWeight: float = Field(default=0.3, ge=0, le=1)
    fusionMethod: Literal["rrf", "weighted"] = "rrf"
    rrfK: int = Field(default=60, ge=1, le=1000)
    keywordAnalyzer: Literal["standard", "cjk", "ik"] = "standard"
    keywordTopK: int = Field(default=50, ge=1, le=500)


class RerankSettingsPayload(BaseModel):
    enabled: bool = False
    provider: Literal["model_center"] = "model_center"
    modelInstanceId: str = Field(default="", max_length=120)
    model: str = Field(default="", max_length=120)
    endpoint: str = Field(default="", max_length=600)
    topK: int = Field(default=20, ge=1, le=200)
    scoreThreshold: float = Field(default=0, ge=0, le=1)
    timeoutSeconds: int = Field(default=10, ge=1, le=120)
    fallbackPolicy: Literal["return_vector_results", "return_empty", "fail"] = "return_vector_results"


class RetrievalSettingsPayload(BaseModel):
    mode: Literal["vector", "hybrid"] = "vector"
    topN: int = Field(default=10, ge=1, le=100)
    candidateTopK: int = Field(default=50, ge=1, le=500)
    scoreThreshold: float = Field(default=0, ge=0, le=1)
    metadataFiltersEnabled: bool = True
    maxChunksPerDocument: int = Field(default=5, ge=1, le=50)
    dedupByDocument: bool = True
    hybrid: HybridSettingsPayload = Field(default_factory=HybridSettingsPayload)
    rerank: RerankSettingsPayload = Field(default_factory=RerankSettingsPayload)

    @model_validator(mode="after")
    def normalize_candidate_top_k(self) -> "RetrievalSettingsPayload":
        if self.candidateTopK < self.topN:
            self.candidateTopK = self.topN
        if self.rerank.topK < self.topN:
            self.rerank.topK = self.topN
        return self


class ContextSettingsPayload(BaseModel):
    includeTitlePath: bool = True
    includePageNo: bool = True
    includeDocumentMeta: bool = True
    neighborChunksBefore: int = Field(default=0, ge=0, le=5)
    neighborChunksAfter: int = Field(default=0, ge=0, le=5)
    maxContextTokens: int = Field(default=6000, ge=500, le=200000)


class CitationSettingsPayload(BaseModel):
    required: bool = True
    returnSourceChunks: bool = True
    returnRawChunkRefs: bool = True
    enablePageJump: bool = True
    maxCount: int = Field(default=5, ge=1, le=50)


class IndexSettingsPayload(BaseModel):
    autoIndexAfterParse: bool = True
    batchSize: int = Field(default=32, ge=1, le=256)
    retryTimes: int = Field(default=3, ge=0, le=10)
    retryIntervalSeconds: int = Field(default=30, ge=1, le=3600)
    versioningEnabled: bool = True


class KnowledgeSettingsPayload(BaseModel):
    parse: KnowledgeParseSettingsPayload = Field(default_factory=KnowledgeParseSettingsPayload)
    embedding: EmbeddingSettingsPayload = Field(default_factory=EmbeddingSettingsPayload)
    vectorStore: VectorStoreSettingsPayload = Field(default_factory=VectorStoreSettingsPayload)
    retrieval: RetrievalSettingsPayload = Field(default_factory=RetrievalSettingsPayload)
    context: ContextSettingsPayload = Field(default_factory=ContextSettingsPayload)
    citation: CitationSettingsPayload = Field(default_factory=CitationSettingsPayload)
    index: IndexSettingsPayload = Field(default_factory=IndexSettingsPayload)


def _main_id(current_user: dict[str, Any]) -> str:
    return str(current_user.get("main_id") or "default")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def default_parse_settings() -> dict[str, int]:
    return {
        "minChunkSize": _default_min_chunk_size(),
        "maxChunkSize": _default_max_chunk_size(),
        "chunkOverlap": _default_chunk_overlap(),
    }


def default_knowledge_settings() -> dict[str, Any]:
    return KnowledgeSettingsPayload().model_dump()


def _deep_merge(defaults: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(defaults)
    for key, value in values.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _camel_config(raw: dict[str, Any]) -> dict[str, Any]:
    if not raw:
        return {}
    parse = raw.get("parse") if isinstance(raw.get("parse"), dict) else {}
    if not parse and any(key in raw for key in ("min_chunk_size", "max_chunk_size", "chunk_size", "chunk_overlap")):
        parse = {
            "minChunkSize": raw.get("min_chunk_size"),
            "maxChunkSize": raw.get("max_chunk_size") or raw.get("chunk_size"),
            "chunkOverlap": raw.get("chunk_overlap"),
        }
    result = dict(raw)
    embedding = dict(result.get("embedding") or {})
    # Legacy deployments could rely on a private Azure env fallback. Public
    # administration now requires an explicit Model Center selection.
    embedding["provider"] = "model_center"
    result["embedding"] = embedding
    retrieval = dict(result.get("retrieval") or {})
    rerank = dict(retrieval.get("rerank") or {})
    rerank["provider"] = "model_center"
    retrieval["rerank"] = rerank
    result["retrieval"] = retrieval
    if parse:
        result["parse"] = {key: value for key, value in parse.items() if value is not None}
    return result


def _serialize_full_settings(doc: dict[str, Any] | None) -> dict[str, Any]:
    config = _camel_config(dict((doc or {}).get("config") or {}))
    merged = _deep_merge(default_knowledge_settings(), config)
    payload = KnowledgeSettingsPayload.model_validate(merged)
    data = payload.model_dump()
    api_key_masked = (doc or {}).get("config", {}).get("vectorStore", {}).get("apiKeyMasked") if doc else ""
    if api_key_masked:
        data["vectorStore"]["apiKeyMasked"] = api_key_masked
    else:
        data["vectorStore"]["apiKeyMasked"] = ""
    data["vectorStore"]["apiKey"] = ""
    data["updatedAt"] = utc_iso((doc or {}).get("updated_at"))
    return data


def serialize_settings(doc: dict[str, Any] | None) -> dict[str, Any]:
    full = _serialize_full_settings(doc)
    parse = full["parse"]
    return {
        "minChunkSize": int(parse["minChunkSize"]),
        "maxChunkSize": int(parse["maxChunkSize"]),
        "chunkSize": int(parse["maxChunkSize"]),
        "chunkOverlap": int(parse["chunkOverlap"]),
        "updatedAt": full["updatedAt"],
    }


async def get_effective_parse_settings(main_id: str) -> dict[str, int]:
    doc = await get_db()[COLLECTION].find_one({"main_id": main_id, "kind": "knowledge"})
    if not doc:
        doc = await get_db()[COLLECTION].find_one({"main_id": main_id, "kind": "parse"})
    serialized = serialize_settings(doc)
    return {
        "minChunkSize": int(serialized["minChunkSize"]),
        "maxChunkSize": int(serialized["maxChunkSize"]),
        "chunkSize": int(serialized["maxChunkSize"]),
        "chunkOverlap": int(serialized["chunkOverlap"]),
    }


async def get_effective_knowledge_settings(main_id: str, *, include_secrets: bool = False) -> dict[str, Any]:
    doc = await get_db()[COLLECTION].find_one({"main_id": main_id, "kind": "knowledge"})
    data = _serialize_full_settings(doc)
    if include_secrets and doc:
        vector_store = dict((doc.get("config") or {}).get("vectorStore") or {})
        if vector_store.get("apiKeyEncrypted"):
            data["vectorStore"]["apiKeyEncrypted"] = str(vector_store.get("apiKeyEncrypted") or "")
    return data


@router.get("")
async def get_knowledge_settings(current_user: dict[str, Any] = Depends(get_current_admin_user)) -> dict[str, Any]:
    doc = await get_db()[COLLECTION].find_one({"main_id": _main_id(current_user), "kind": "knowledge"})
    return _serialize_full_settings(doc)


@router.put("")
async def save_knowledge_settings(
    payload: KnowledgeSettingsPayload,
    current_user: dict[str, Any] = Depends(get_current_admin_user),
) -> dict[str, Any]:
    main_id = _main_id(current_user)
    try:
        embedding_instance = await find_instance_by_id(payload.embedding.modelInstanceId, main_id)
    except InvalidId as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请选择有效的向量模型",
        ) from exc
    if (
        embedding_instance is None
        or embedding_instance.get("status") != "active"
        or "embedding" not in list(embedding_instance.get("capabilities") or [])
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="向量模型不存在、已禁用或不支持向量能力",
        )
    if payload.retrieval.rerank.enabled:
        try:
            rerank_instance = await find_instance_by_id(payload.retrieval.rerank.modelInstanceId, main_id)
        except InvalidId as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="请选择有效的重排模型",
            ) from exc
        if (
            rerank_instance is None
            or rerank_instance.get("status") != "active"
            or "rerank" not in list(rerank_instance.get("capabilities") or [])
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="重排模型不存在、已禁用或不支持重排能力",
            )
    now = _now()
    config = payload.model_dump()
    existing = await get_db()[COLLECTION].find_one({"main_id": main_id, "kind": "knowledge"})
    vector_store = dict(config.get("vectorStore") or {})
    api_key = str(vector_store.pop("apiKey", "") or "")
    if api_key:
        vector_store["apiKeyEncrypted"] = encrypt_secret(api_key)
        vector_store["apiKeyMasked"] = mask_secret(api_key)
    elif existing:
        old_vector_store = dict((existing.get("config") or {}).get("vectorStore") or {})
        if old_vector_store.get("apiKeyEncrypted"):
            vector_store["apiKeyEncrypted"] = old_vector_store.get("apiKeyEncrypted")
            vector_store["apiKeyMasked"] = old_vector_store.get("apiKeyMasked", "")
    config["vectorStore"] = vector_store
    await get_db()[COLLECTION].update_one(
        {"main_id": main_id, "kind": "knowledge"},
        {
            "$set": {
                "config": config,
                "updated_by": str(current_user.get("username") or ""),
                "updated_at": now,
            },
            "$setOnInsert": {
                "main_id": main_id,
                "kind": "knowledge",
                "created_at": now,
            },
        },
        upsert=True,
    )
    doc = await get_db()[COLLECTION].find_one({"main_id": main_id, "kind": "knowledge"})
    return _serialize_full_settings(doc)


@router.get("/parse")
async def get_parse_settings(current_user: dict[str, Any] = Depends(get_current_admin_user)) -> dict[str, Any]:
    main_id = _main_id(current_user)
    doc = await get_db()[COLLECTION].find_one({"main_id": main_id, "kind": "knowledge"})
    if not doc:
        doc = await get_db()[COLLECTION].find_one({"main_id": main_id, "kind": "parse"})
    return serialize_settings(doc)


@router.put("/parse")
async def save_parse_settings(
    payload: KnowledgeParseSettingsPayload,
    current_user: dict[str, Any] = Depends(get_current_admin_user),
) -> dict[str, Any]:
    main_id = _main_id(current_user)
    now = _now()
    doc = await get_db()[COLLECTION].find_one({"main_id": main_id, "kind": "knowledge"})
    full = _serialize_full_settings(doc)
    max_chunk_size = int(payload.maxChunkSize)
    full["parse"] = {
        "minChunkSize": min(int(payload.minChunkSize), max_chunk_size),
        "maxChunkSize": max_chunk_size,
        "chunkOverlap": int(payload.chunkOverlap),
    }
    vector_store = dict(full.get("vectorStore") or {})
    vector_store.pop("apiKey", None)
    vector_store.pop("apiKeyMasked", None)
    if doc:
        old_vector_store = dict((doc.get("config") or {}).get("vectorStore") or {})
        if old_vector_store.get("apiKeyEncrypted"):
            vector_store["apiKeyEncrypted"] = old_vector_store.get("apiKeyEncrypted")
            vector_store["apiKeyMasked"] = old_vector_store.get("apiKeyMasked", "")
    full["vectorStore"] = vector_store
    full.pop("updatedAt", None)
    await get_db()[COLLECTION].update_one(
        {"main_id": main_id, "kind": "knowledge"},
        {
            "$set": {
                "config": full,
                "updated_by": str(current_user.get("username") or ""),
                "updated_at": now,
            },
            "$setOnInsert": {
                "main_id": main_id,
                "kind": "knowledge",
                "created_at": now,
            },
        },
        upsert=True,
    )
    doc = await get_db()[COLLECTION].find_one({"main_id": main_id, "kind": "knowledge"})
    return serialize_settings(doc)


async def ensure_indexes() -> None:
    await get_db()[COLLECTION].create_index([("main_id", 1), ("kind", 1)], unique=True)
