from __future__ import annotations

import asyncio
import json
import ssl
import urllib.parse
import urllib.request
from typing import Any

try:
    import certifi
except Exception:  # pragma: no cover - optional dependency
    certifi = None

from app.core.config import settings


PROVIDERS: dict[str, dict[str, Any]] = {
    "tavily": {
        "label": "Tavily",
        "description": "面向 AI 应用的网页搜索，配置最简单。",
        "endpoint": "",
        "base_url": "",
        "model": "",
        "priority": 10,
    },
    "serper": {
        "label": "Serper",
        "description": "通过 Google 搜索结果 API 提供快速、结构化的网页检索。",
        "endpoint": "https://google.serper.dev/search",
        "base_url": "",
        "model": "",
        "priority": 20,
    },
    "serpapi": {
        "label": "SerpAPI",
        "description": "聚合 Google 等搜索引擎结果，适合需要标准 SERP 数据的场景。",
        "endpoint": "https://serpapi.com/search.json",
        "base_url": "",
        "model": "",
        "priority": 30,
    },
    "baidu_qianfan": {
        "label": "百度千帆",
        "description": "适合以中文网页和百度搜索结果为主的场景。",
        "endpoint": "https://qianfan.baidubce.com/v2/ai_search/web_search",
        "base_url": "",
        "model": "",
        "priority": 40,
    },
    "volc_ark": {
        "label": "火山 Ark",
        "description": "通过已启用联网能力的 Ark Bot 获取搜索结果。",
        "endpoint": "",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3/bots",
        "model": "",
        "priority": 50,
    },
}


class ExternalSearchConfigError(ValueError):
    pass


def provider_or_error(provider: str) -> str:
    token = str(provider or "").strip()
    if token not in PROVIDERS:
        raise ExternalSearchConfigError("搜索源不存在")
    return token


def normalized_config(
    provider: str,
    *,
    api_key: str,
    endpoint: str = "",
    base_url: str = "",
    model: str = "",
) -> dict[str, str]:
    token = provider_or_error(provider)
    meta = PROVIDERS[token]
    config = {
        "api_key": str(api_key or "").strip(),
        "endpoint": str(endpoint or "").strip() or str(meta["endpoint"]),
        "base_url": str(base_url or "").strip() or str(meta["base_url"]),
        "model": str(model or "").strip() or str(meta["model"]),
    }
    if not config["api_key"]:
        raise ExternalSearchConfigError("请填写 API Key")
    if token == "baidu_qianfan" and not config["endpoint"]:
        raise ExternalSearchConfigError("请填写 Endpoint")
    if token == "volc_ark" and (not config["base_url"] or not config["model"]):
        raise ExternalSearchConfigError("请填写 Base URL 和 Bot Model")
    return config


def _ssl_context() -> ssl.SSLContext:
    if settings.model_test_insecure_skip_verify:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context
    if settings.model_test_ca_bundle.strip():
        return ssl.create_default_context(cafile=settings.model_test_ca_bundle.strip())
    if certifi is not None:
        try:
            return ssl.create_default_context(cafile=certifi.where())
        except Exception:
            pass
    return ssl.create_default_context()


def _post_json(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=25.0, context=_ssl_context()) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def _get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{url}?{query}", headers={"Accept": "application/json"}, method="GET")
    with urllib.request.urlopen(request, timeout=25.0, context=_ssl_context()) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def _reference_rows(items: Any) -> list[dict[str, str]]:
    return [
        {
            "title": str(item.get("title") or item.get("site_name") or ""),
            "url": str(item.get("url") or item.get("link") or ""),
            "snippet": str(item.get("snippet") or item.get("summary") or item.get("content") or "")[:300],
        }
        for item in list(items or [])[:3]
        if isinstance(item, dict)
    ]


def _collect_references(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        refs = value.get("references") or value.get("citations") or value.get("sources")
        if isinstance(refs, list):
            found.extend(item for item in refs if isinstance(item, dict))
        for nested in value.values():
            found.extend(_collect_references(nested))
    elif isinstance(value, list):
        for item in value:
            found.extend(_collect_references(item))
    return found


def _extract_answer(value: dict[str, Any]) -> str:
    choices = value.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first.get("message"), dict) else {}
        content = message.get("content") or first.get("text")
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            parts = [str(item.get("text") or item.get("content") or "") for item in content if isinstance(item, dict)]
            if any(parts):
                return "\n".join(part for part in parts if part).strip()
    output = value.get("output")
    if isinstance(output, str):
        return output.strip()
    if isinstance(output, dict):
        return str(output.get("text") or output.get("content") or "").strip()
    return ""


async def test_provider(provider: str, config: dict[str, str], query: str) -> list[dict[str, str]]:
    token = provider_or_error(provider)
    search_query = str(query or "").strip() or "MOVO enterprise AI"

    def run() -> list[dict[str, str]]:
        if token == "tavily":
            data = _post_json(
                "https://api.tavily.com/search",
                {"Content-Type": "application/json", "Authorization": f"Bearer {config['api_key']}"},
                {"api_key": config["api_key"], "query": search_query, "search_depth": "basic", "max_results": 3},
            )
            return _reference_rows(data.get("results"))
        if token == "serper":
            data = _post_json(
                config["endpoint"],
                {"Content-Type": "application/json", "X-API-KEY": config["api_key"]},
                {"q": search_query, "num": 3},
            )
            return _reference_rows(data.get("organic"))
        if token == "serpapi":
            data = _get_json(
                config["endpoint"],
                {"engine": "google", "q": search_query, "api_key": config["api_key"], "num": 3},
            )
            return _reference_rows(data.get("organic_results"))
        if token == "baidu_qianfan":
            data = _post_json(
                config["endpoint"],
                {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {config['api_key']}",
                    "X-Appbuilder-Authorization": f"Bearer {config['api_key']}",
                },
                {
                    "messages": [{"content": search_query, "role": "user"}],
                    "edition": "standard",
                    "search_source": "baidu_search_v2",
                    "resource_type_filter": [{"type": "web", "top_k": 3}],
                },
            )
            return _reference_rows(data.get("references"))

        data = _post_json(
            f"{config['base_url'].rstrip('/')}/chat/completions",
            {"Content-Type": "application/json", "Authorization": f"Bearer {config['api_key']}"},
            {
                "model": config["model"],
                "messages": [
                    {"role": "system", "content": "你是一个联网搜索助手，请根据用户问题搜索互联网并返回引用。"},
                    {"role": "user", "content": search_query},
                ],
            },
        )
        rows = [row for row in _reference_rows(_collect_references(data)) if any(row.values())]
        if rows:
            return rows
        answer = _extract_answer(data)
        return [{"title": "Ark Bot response", "url": "", "snippet": answer[:300]}] if answer else []

    return await asyncio.to_thread(run)
