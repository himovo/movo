from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from app.core.config import settings
from app.services.model_center_runtime import ModelCenterConfigError, resolve_model_instance


class RerankerError(RuntimeError):
    pass


def rerank(query: str, candidates: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    retrieval = dict(config.get("retrieval") or {})
    rerank_config = dict(retrieval.get("rerank") or {})
    if not bool(rerank_config.get("enabled", False)):
        return candidates
    provider = str(rerank_config.get("provider") or "model_center")
    try:
        if provider == "model_center":
            return _model_center_rerank(query, candidates, rerank_config, str(config.get("_mainId") or ""))
        if provider != "dashscope_qwen":
            raise RerankerError(f"不支持的 rerank provider: {provider}")
        return _dashscope_rerank(query, candidates, rerank_config)
    except Exception:
        fallback = str(rerank_config.get("fallbackPolicy") or "return_vector_results")
        if fallback == "return_vector_results":
            return candidates
        if fallback == "return_empty":
            return []
        raise


def _dashscope_rerank(query: str, candidates: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    api_key = settings.dashscope_api_key.strip()
    endpoint = str(config.get("endpoint") or "").strip()
    model = str(config.get("model") or "qwen3-vl-rerank").strip()
    top_n = int(config.get("topK") or len(candidates) or 1)
    timeout = int(config.get("timeoutSeconds") or 10)
    threshold = float(config.get("scoreThreshold") or 0)
    if not api_key:
        raise RerankerError("DASHSCOPE_API_KEY 未配置")
    if not endpoint:
        raise RerankerError("DashScope rerank endpoint 未配置")
    documents = _candidate_documents(candidates)
    payload = {
        "model": model,
        "input": {"query": query, "documents": documents},
        "parameters": {"return_documents": True, "top_n": max(1, min(top_n, len(documents) or 1))},
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.URLError as exc:
        raise RerankerError(f"DashScope rerank 调用失败: {exc}") from exc
    return _merge_results(candidates, _extract_results(body), top_n=top_n, threshold=threshold)


def _model_center_rerank(
    query: str, candidates: list[dict[str, Any]], config: dict[str, Any], main_id: str
) -> list[dict[str, Any]]:
    try:
        runtime = resolve_model_instance(main_id, str(config.get("modelInstanceId") or ""), "rerank")
    except ModelCenterConfigError as exc:
        raise RerankerError(str(exc)) from exc
    documents = _candidate_documents(candidates)
    top_n = max(1, min(int(config.get("topK") or len(documents) or 1), len(documents) or 1))
    threshold = float(config.get("scoreThreshold") or 0)
    timeout = int(config.get("timeoutSeconds") or 10)
    base_url = runtime["baseUrl"]
    provider_code = runtime["providerCode"]
    is_dashscope = provider_code == "qwen" or "dashscope.aliyuncs.com" in base_url
    if is_dashscope:
        endpoint = base_url if "/rerank/" in base_url else "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
        payload = {
            "model": runtime["modelName"],
            "input": {"query": query, "documents": documents},
            "parameters": {"return_documents": True, "top_n": top_n},
        }
    else:
        endpoint = base_url if base_url.rstrip("/").endswith("/rerank") else f"{base_url}/rerank"
        payload = {"model": runtime["modelName"], "query": query, "documents": documents, "top_n": top_n}
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {runtime['apiKey']}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RerankerError(f"Rerank 请求失败: HTTP {exc.code} {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RerankerError(f"Rerank 调用失败: {exc}") from exc
    return _merge_results(candidates, _extract_results(body), top_n=top_n, threshold=threshold)


def _candidate_documents(candidates: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("contextualText") or item.get("text") or "") for item in candidates]


def _merge_results(
    candidates: list[dict[str, Any]], results: list[dict[str, Any]], *, top_n: int, threshold: float
) -> list[dict[str, Any]]:
    if not results:
        return candidates[:top_n]
    output: list[dict[str, Any]] = []
    for result in results:
        index = int(result.get("index") if result.get("index") is not None else result.get("document_index") or -1)
        if index < 0 or index >= len(candidates):
            continue
        score = float(result.get("relevance_score") or result.get("score") or 0)
        if threshold and score < threshold:
            continue
        item = dict(candidates[index])
        item["rerankScore"] = score
        output.append(item)
    return output[:top_n]


def _extract_results(body: dict[str, Any]) -> list[dict[str, Any]]:
    output = body.get("output")
    if isinstance(output, dict):
        for key in ("results", "documents"):
            value = output.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    for key in ("results", "documents"):
        value = body.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []
