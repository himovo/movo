from __future__ import annotations

import json
import re
import uuid
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app.core.config import settings
from app.services.secret_codec import decrypt_admin_secret


class VectorStoreError(RuntimeError):
    pass


def get_vector_store(config: dict[str, Any]) -> "WeaviateVectorStore":
    configured_store = dict(config.get("vectorStore") or {})
    configured_endpoint = str(configured_store.get("endpoint") or "").rstrip("/")
    env_endpoint = str(settings.weaviate_endpoint or "").rstrip("/")
    if _is_local_default_endpoint(configured_endpoint) and env_endpoint and not _is_local_default_endpoint(env_endpoint):
        configured_store["endpoint"] = env_endpoint

    vector_config = {
        "type": "weaviate",
        "endpoint": settings.weaviate_endpoint,
        "apiKey": settings.weaviate_api_key,
        "collectionName": settings.weaviate_collection_name,
        "distanceMetric": settings.weaviate_distance_metric,
        **configured_store,
    }
    store_type = str(vector_config.get("type") or "weaviate")
    if store_type != "weaviate":
        raise VectorStoreError(f"向量库 {store_type} 已预留，当前默认实现为 Weaviate")
    return WeaviateVectorStore(vector_config)


class WeaviateVectorStore:
    def __init__(self, config: dict[str, Any]) -> None:
        self.endpoint = str(config.get("endpoint") or "http://127.0.0.1:8080").rstrip("/")
        self.collection = _sanitize_class_name(str(config.get("collectionName") or "AskAIKnowledgeChunks"))
        self.distance = str(config.get("distanceMetric") or "cosine").lower()
        self.api_key = str(config.get("apiKey") or "") or decrypt_admin_secret(str(config.get("apiKeyEncrypted") or ""))

    def ensure_schema(self) -> None:
        schema = self._request_json("GET", f"/v1/schema/{self.collection}", allow_404=True)
        if schema:
            return
        body = {
            "class": self.collection,
            "description": "MOVO knowledge RAG chunks",
            "vectorizer": "none",
            "vectorIndexConfig": {"distance": _weaviate_distance(self.distance)},
            "properties": [
                {"name": "mainId", "dataType": ["text"]},
                {"name": "knowledgeBaseId", "dataType": ["text"]},
                {"name": "documentId", "dataType": ["text"]},
                {"name": "chunkId", "dataType": ["text"]},
                {"name": "chunkStage", "dataType": ["text"]},
                {"name": "text", "dataType": ["text"]},
                {"name": "contextualText", "dataType": ["text"]},
                {"name": "titlePath", "dataType": ["text[]"]},
                {"name": "pageNo", "dataType": ["int"]},
                {"name": "contentType", "dataType": ["text"]},
                {"name": "sourceChunkIds", "dataType": ["text[]"]},
                {"name": "ordinal", "dataType": ["int"]},
            ],
        }
        self._request_json("POST", "/v1/schema", body)

    def delete_document_chunks(self, *, main_id: str, document_id: str) -> int:
        if not main_id or not document_id:
            return 0
        schema = self._request_json("GET", f"/v1/schema/{self.collection}", allow_404=True)
        if not schema:
            return 0
        where = {
            "operator": "And",
            "operands": [
                {"path": ["mainId"], "operator": "Equal", "valueText": main_id},
                {"path": ["documentId"], "operator": "Equal", "valueText": document_id},
            ],
        }
        body = self._request_json(
            "DELETE",
            "/v1/batch/objects",
            {
                "match": {
                    "class": self.collection,
                    "where": where,
                },
                "output": "minimal",
            },
        )
        if isinstance(body, dict):
            result = body.get("results") or body.get("result") or {}
            matches = result.get("matches") if isinstance(result, dict) else None
            successful = result.get("successful") if isinstance(result, dict) else None
            for value in (successful, matches):
                try:
                    if value is not None:
                        return int(value)
                except (TypeError, ValueError):
                    continue
        return 0

    def upsert_chunks(self, chunks: list[dict[str, Any]], vectors: list[list[float]]) -> int:
        if len(chunks) != len(vectors):
            raise VectorStoreError("chunk 数量和向量数量不一致")
        objects = []
        for chunk, vector in zip(chunks, vectors):
            object_id = _stable_uuid(str(chunk.get("main_id") or ""), str(chunk.get("document_id") or ""), str(chunk.get("chunk_id") or ""))
            properties = {
                "mainId": str(chunk.get("main_id") or ""),
                "knowledgeBaseId": str(chunk.get("knowledge_base_id") or ""),
                "documentId": str(chunk.get("document_id") or ""),
                "chunkId": str(chunk.get("chunk_id") or ""),
                "chunkStage": str(chunk.get("chunk_stage") or "rag"),
                "text": str(chunk.get("text") or ""),
                "contextualText": str(chunk.get("contextual_text") or chunk.get("text") or ""),
                "titlePath": [str(item) for item in chunk.get("title_path") or []],
                "pageNo": chunk.get("page_no"),
                "contentType": str(chunk.get("content_type") or "text"),
                "sourceChunkIds": [str(item) for item in chunk.get("source_chunk_ids") or []],
                "ordinal": int(chunk.get("ordinal") or 0),
            }
            if properties["pageNo"] is None:
                properties.pop("pageNo", None)
            objects.append(
                {
                    "class": self.collection,
                    "id": object_id,
                    "properties": properties,
                    "vector": vector,
                }
            )
        body = self._request_json("POST", "/v1/batch/objects", {"objects": objects})
        errors = [item for item in body if isinstance(item, dict) and item.get("result", {}).get("errors")] if isinstance(body, list) else []
        if errors:
            raise VectorStoreError(f"Weaviate batch upsert failed: {errors[:1]}")
        return len(objects)

    def search(
        self,
        *,
        query_vector: list[float],
        query: str,
        main_id: str,
        knowledge_base_id: str,
        mode: str,
        limit: int,
        score_threshold: float,
    ) -> list[dict[str, Any]]:
        where_operands = [{"path": ["mainId"], "operator": "Equal", "valueText": main_id}]
        if knowledge_base_id:
            where_operands.append({"path": ["knowledgeBaseId"], "operator": "Equal", "valueText": knowledge_base_id})
        where = {"operator": "And", "operands": where_operands}
        fields = "mainId knowledgeBaseId documentId chunkId chunkStage text contextualText titlePath pageNo contentType sourceChunkIds ordinal _additional { distance score }"
        if mode == "hybrid":
            hybrid = _graphql_value({"query": query, "vector": query_vector, "alpha": 0.7})
            selector = f'hybrid: {hybrid}'
        else:
            near_vector = _graphql_value({"vector": query_vector})
            selector = f'nearVector: {near_vector}'
        where_text = _graphql_value(where)
        graphql = {
            "query": f"{{ Get {{ {self.collection}({selector}, where: {where_text}, limit: {int(limit)}) {{ {fields} }} }} }}"
        }
        body = self._request_json("POST", "/v1/graphql", graphql)
        if isinstance(body, dict) and body.get("errors"):
            raise VectorStoreError(f"Weaviate GraphQL failed: {body.get('errors')}")
        rows = (((body.get("data") or {}).get("Get") or {}).get(self.collection) or []) if isinstance(body, dict) else []
        results: list[dict[str, Any]] = []
        for row in rows:
            additional = row.get("_additional") or {}
            distance = additional.get("distance")
            score = additional.get("score")
            normalized = _normalize_score(score, distance)
            if score_threshold and normalized < score_threshold:
                continue
            results.append(
                {
                    "documentId": str(row.get("documentId") or ""),
                    "chunkId": str(row.get("chunkId") or ""),
                    "chunkStage": str(row.get("chunkStage") or "rag"),
                    "text": str(row.get("text") or ""),
                    "contextualText": str(row.get("contextualText") or row.get("text") or ""),
                    "titlePath": list(row.get("titlePath") or []),
                    "pageNo": row.get("pageNo"),
                    "contentType": str(row.get("contentType") or "text"),
                    "sourceChunkIds": list(row.get("sourceChunkIds") or []),
                    "ordinal": int(row.get("ordinal") or 0),
                    "score": normalized,
                    "distance": distance,
                }
            )
        return results

    def _request_json(self, method: str, path: str, body: dict[str, Any] | None = None, *, allow_404: bool = False) -> Any:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            f"{self.endpoint}{path}",
            data=data,
            headers=self._headers(),
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            if allow_404 and exc.code == 404:
                return {}
            detail = exc.read().decode("utf-8", errors="replace")
            raise VectorStoreError(f"Weaviate request failed: HTTP {exc.code} {detail[:500]}") from exc
        except urllib.error.URLError as exc:
            raise VectorStoreError(f"Weaviate unavailable: {exc}") from exc

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers


def _sanitize_class_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "", value or "")
    if not cleaned:
        return "AskAIKnowledgeChunks"
    if not cleaned[0].isalpha():
        cleaned = f"AskAI{cleaned}"
    return cleaned[:120]


def _weaviate_distance(value: str) -> str:
    return {"cosine": "cosine", "dot": "dot", "l2": "l2-squared"}.get(value, "cosine")


def _is_local_default_endpoint(value: str) -> bool:
    normalized = (value or "").rstrip("/")
    return normalized in {
        "",
        "http://127.0.0.1:8080",
        "https://127.0.0.1:8080",
        "http://localhost:8080",
        "https://localhost:8080",
    }


def _stable_uuid(*parts: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, ":".join(parts)))


def _normalize_score(score: Any, distance: Any) -> float:
    try:
        if distance is not None:
            return max(0.0, 1.0 - float(distance))
        if score is not None:
            return float(score)
    except (TypeError, ValueError):
        return 0.0
    return 0.0


def _graphql_value(value: Any, *, key: str = "") -> str:
    if isinstance(value, dict):
        return "{" + ", ".join(f"{item_key}: {_graphql_value(item, key=item_key)}" for item_key, item in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(_graphql_value(item) for item in value) + "]"
    if isinstance(value, str):
        if key == "operator":
            return value
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)
