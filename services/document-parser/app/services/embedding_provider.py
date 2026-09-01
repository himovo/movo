from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from app.core.config import settings
from app.services.model_center_runtime import ModelCenterConfigError, resolve_model_instance


class EmbeddingProviderError(RuntimeError):
    pass


def embed_texts(texts: list[str], config: dict[str, Any]) -> list[list[float]]:
    embedding_config = dict(config.get("embedding") or {})
    provider = str(embedding_config.get("provider") or "model_center")
    if provider == "model_center":
        try:
            runtime = resolve_model_instance(
                str(config.get("_mainId") or ""),
                str(embedding_config.get("modelInstanceId") or ""),
                "embedding",
            )
        except ModelCenterConfigError as exc:
            raise EmbeddingProviderError(str(exc)) from exc
        return _model_center_embed_texts(
            texts,
            runtime=runtime,
            batch_size=int(embedding_config.get("batchSize") or 32),
            timeout=int(embedding_config.get("timeoutSeconds") or 30),
        )
    if provider != "default_azure":
        raise EmbeddingProviderError(f"不支持的 embedding provider: {provider}")
    return _azure_embed_texts(
        texts,
        batch_size=int(embedding_config.get("batchSize") or 32),
        timeout=int(embedding_config.get("timeoutSeconds") or 30),
    )


def embed_query(query: str, config: dict[str, Any]) -> list[float]:
    embeddings = embed_texts([query], config)
    if not embeddings:
        raise EmbeddingProviderError("embedding service returned empty result")
    return embeddings[0]


def _azure_embed_texts(texts: list[str], *, batch_size: int, timeout: int) -> list[list[float]]:
    endpoint = settings.azure_embedding_endpoint.rstrip("/")
    deployment = settings.azure_embedding_deployment_name.strip()
    api_key = settings.azure_embedding_api_key.strip()
    api_version = settings.azure_embedding_api_version.strip() or "2025-04-01-preview"
    if not endpoint or not deployment or not api_key:
        raise EmbeddingProviderError("Azure embedding 配置不完整，请设置 endpoint、deployment 和 API Key")

    results: list[list[float]] = []
    batch = max(1, min(batch_size, 256))
    for start in range(0, len(texts), batch):
        current = texts[start : start + batch]
        payload = json.dumps({"input": current}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{endpoint}/openai/deployments/{deployment}/embeddings?api-version={api_version}",
            data=payload,
            headers={
                "api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        body = _open_json_with_retry(request, timeout=timeout)
        data = body.get("data")
        if not isinstance(data, list):
            raise EmbeddingProviderError("Azure embedding 返回格式不正确")
        ordered = sorted(data, key=lambda item: int(item.get("index") or 0))
        for item in ordered:
            embedding = item.get("embedding")
            if not isinstance(embedding, list):
                raise EmbeddingProviderError("Azure embedding 缺少 embedding 字段")
            results.append([float(value) for value in embedding])
    return results


def _model_center_embed_texts(
    texts: list[str], *, runtime: dict[str, str], batch_size: int, timeout: int
) -> list[list[float]]:
    base_url = runtime["baseUrl"]
    model_name = runtime["modelName"]
    api_key = runtime["apiKey"]
    if not base_url or not model_name:
        raise EmbeddingProviderError("模型中心 embedding 的 Base URL 或模型 ID 为空")
    is_azure = runtime["providerType"] == "azure_openai"
    if is_azure:
        api_version = runtime["apiVersion"] or "2025-04-01-preview"
        url = f"{base_url}/openai/deployments/{model_name}/embeddings?api-version={api_version}"
        headers = {"api-key": api_key, "Content-Type": "application/json", "Accept": "application/json"}
    else:
        url = base_url if base_url.endswith("/embeddings") else f"{base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
    results: list[list[float]] = []
    batch = max(1, min(batch_size, 256))
    for start in range(0, len(texts), batch):
        current = texts[start : start + batch]
        payload: dict[str, Any] = {"input": current}
        if not is_azure:
            payload["model"] = model_name
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        body = _open_json_with_retry(request, timeout=timeout)
        data = body.get("data")
        if not isinstance(data, list):
            raise EmbeddingProviderError("模型中心 embedding 返回格式不正确")
        for item in sorted(data, key=lambda value: int(value.get("index") or 0)):
            embedding = item.get("embedding")
            if not isinstance(embedding, list):
                raise EmbeddingProviderError("模型中心 embedding 缺少 embedding 字段")
            results.append([float(value) for value in embedding])
    return results


def _open_json_with_retry(request: urllib.request.Request, *, timeout: int) -> dict[str, Any]:
    attempts = 3
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                body = json.loads(raw) if raw else {}
                return body if isinstance(body, dict) else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise EmbeddingProviderError(f"Embedding 请求失败: HTTP {exc.code} {detail[:500]}") from exc
        except urllib.error.URLError as exc:
            last_exc = exc
            if attempt >= attempts - 1:
                break
            time.sleep(0.4 * (attempt + 1))
    raise EmbeddingProviderError(f"Embedding 调用失败: {last_exc}") from last_exc
