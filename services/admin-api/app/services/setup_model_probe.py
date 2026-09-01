from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class SetupModelProbeError(RuntimeError):
    pass


@dataclass(frozen=True)
class SetupKnowledgeProbeResult:
    message: str
    dimension: int | None = None


def probe_knowledge_model(normalized: dict[str, Any], provider: dict[str, Any]) -> str:
    return probe_knowledge_model_details(normalized, provider).message


def probe_knowledge_model_details(
    normalized: dict[str, Any],
    provider: dict[str, Any],
) -> SetupKnowledgeProbeResult:
    capability = str((normalized.get("capabilities") or [""])[0])
    if capability == "embedding":
        return _probe_embedding(normalized, provider)
    if capability == "rerank":
        return _probe_rerank(normalized, provider)
    raise SetupModelProbeError(f"Unsupported knowledge model probe: {capability}")


def _probe_embedding(model: dict[str, Any], provider: dict[str, Any]) -> SetupKnowledgeProbeResult:
    base_url = str(model.get("base_url") or "").rstrip("/")
    model_name = str(model.get("model_name") or "")
    api_key = str(model.get("api_key") or "")
    if str(provider.get("provider_type") or "") == "azure_openai":
        api_version = str(model.get("api_version") or "2025-04-01-preview")
        url = f"{base_url}/openai/deployments/{model_name}/embeddings?api-version={api_version}"
        headers = {"api-key": api_key, "Content-Type": "application/json"}
        payload = {"input": ["MOVO knowledge model connectivity test"]}
    else:
        url = base_url if base_url.endswith("/embeddings") else f"{base_url}/embeddings"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"model": model_name, "input": ["MOVO knowledge model connectivity test"]}
    body = _post_json(url, headers, payload)
    data = body.get("data")
    if not isinstance(data, list) or not data or not isinstance(data[0].get("embedding"), list):
        raise SetupModelProbeError("Embedding service returned an invalid response.")
    dimension = len(data[0]["embedding"])
    return SetupKnowledgeProbeResult(
        message=f"Embedding connection succeeded ({dimension} dimensions).",
        dimension=dimension,
    )


def _probe_rerank(model: dict[str, Any], provider: dict[str, Any]) -> SetupKnowledgeProbeResult:
    base_url = str(model.get("base_url") or "").rstrip("/")
    provider_code = str(provider.get("code") or "")
    is_dashscope = provider_code == "qwen" or "dashscope.aliyuncs.com" in base_url
    if is_dashscope:
        url = base_url if "/rerank/" in base_url else "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
        payload = {
            "model": str(model.get("model_name") or ""),
            "input": {"query": "MOVO", "documents": ["MOVO enterprise AI", "unrelated text"]},
            "parameters": {"return_documents": False, "top_n": 1},
        }
    else:
        url = base_url if base_url.endswith("/rerank") else f"{base_url}/rerank"
        payload = {
            "model": str(model.get("model_name") or ""),
            "query": "MOVO",
            "documents": ["MOVO enterprise AI", "unrelated text"],
            "top_n": 1,
        }
    body = _post_json(
        url,
        {"Authorization": f"Bearer {model.get('api_key') or ''}", "Content-Type": "application/json"},
        payload,
    )
    output = body.get("output") if isinstance(body.get("output"), dict) else body
    results = output.get("results") if isinstance(output, dict) else None
    if not isinstance(results, list):
        raise SetupModelProbeError("Rerank service returned an invalid response.")
    return SetupKnowledgeProbeResult(message="Rerank connection succeeded.")


def _post_json(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={**headers, "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SetupModelProbeError(f"Model service returned HTTP {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise SetupModelProbeError(f"Unable to reach model service: {exc.reason}") from exc
    if not isinstance(body, dict):
        raise SetupModelProbeError("Model service returned an invalid response.")
    return body
