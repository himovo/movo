from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol

import httpx

from app.core.config import get_settings
from app.llm.factory import get_openai_compatible_client
from app.llm.types import Message, Role
from app.enterprise_capabilities.research.progressive.models import SearchCandidate
from app.infrastructure.request_context import get_request_context
from app.services.search_provider_config import resolve_default_external_search_provider


logger = logging.getLogger(__name__)


class SearchProvider(Protocol):
    name: str

    async def search(self, query: str, *, max_results: int) -> list[SearchCandidate]:
        ...


class TavilyProvider:
    name = "tavily"

    def __init__(self, *, api_key: str) -> None:
        self.api_key = api_key

    async def search(self, query: str, *, max_results: int) -> list[SearchCandidate]:
        def _run() -> list[SearchCandidate]:
            try:
                from tavily import TavilyClient  # type: ignore
            except Exception as exc:
                logger.warning("progressive_research_tavily_import_failed error=%s", exc)
                return []
            try:
                resp = TavilyClient(api_key=self.api_key).search(
                    query=query,
                    search_depth="advanced",
                    max_results=max(1, min(20, int(max_results or 8))),
                )
            except Exception as exc:
                logger.warning("progressive_research_tavily_failed query=%r error=%s", query[:120], exc)
                return []
            rows: list[SearchCandidate] = []
            for item in list(resp.get("results") or []):
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url") or "").strip()
                if not url:
                    continue
                rows.append(
                    SearchCandidate(
                        provider=self.name,
                        query=query,
                        title=str(item.get("title") or "").strip(),
                        url=url,
                        snippet=str(item.get("content") or "").strip(),
                        score=float(item.get("score") or 0.0),
                    )
                )
            return rows

        return await asyncio.to_thread(_run)


class SerperProvider:
    name = "serper"

    def __init__(self, *, api_key: str) -> None:
        self.api_key = api_key

    async def search(self, query: str, *, max_results: int) -> list[SearchCandidate]:
        payload = {"q": query, "num": max(1, min(20, int(max_results or 8)))}
        headers = {"X-API-KEY": self.api_key, "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
                resp = await client.post("https://google.serper.dev/search", json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("progressive_research_serper_failed query=%r error=%s", query[:120], exc)
            return []
        rows: list[SearchCandidate] = []
        for item in list(data.get("organic") or []):
            if not isinstance(item, dict):
                continue
            url = str(item.get("link") or "").strip()
            if not url:
                continue
            rows.append(
                SearchCandidate(
                    provider=self.name,
                    query=query,
                    title=str(item.get("title") or "").strip(),
                    url=url,
                    snippet=str(item.get("snippet") or "").strip(),
                    score=None,
                )
            )
        return rows


class SerpApiProvider:
    name = "serpapi"

    def __init__(self, *, api_key: str) -> None:
        self.api_key = api_key

    async def search(self, query: str, *, max_results: int) -> list[SearchCandidate]:
        params = {
            "engine": "google",
            "q": query,
            "api_key": self.api_key,
            "num": max(1, min(20, int(max_results or 8))),
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
                resp = await client.get("https://serpapi.com/search.json", params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("progressive_research_serpapi_failed query=%r error=%s", query[:120], exc)
            return []
        rows: list[SearchCandidate] = []
        for item in list(data.get("organic_results") or []):
            if not isinstance(item, dict):
                continue
            url = str(item.get("link") or "").strip()
            if not url:
                continue
            rows.append(
                SearchCandidate(
                    provider=self.name,
                    query=query,
                    title=str(item.get("title") or "").strip(),
                    url=url,
                    snippet=str(item.get("snippet") or "").strip(),
                    score=None,
                )
            )
        return rows


class BaiduQianfanProvider:
    name = "baidu_qianfan"

    def __init__(self, *, api_key: str, endpoint: str) -> None:
        self.api_key = api_key
        self.endpoint = endpoint

    async def search(self, query: str, *, max_results: int) -> list[SearchCandidate]:
        if not self.api_key or not self.endpoint:
            logger.warning("progressive_research_qianfan_skipped reason=missing_api_key_or_endpoint")
            return []
        payload = {
            "messages": [{"content": query, "role": "user"}],
            "edition": "standard",
            "search_source": "baidu_search_v2",
            "resource_type_filter": [{"type": "web", "top_k": max(1, min(20, int(max_results or 8)))}],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-Appbuilder-Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
                resp = await client.post(self.endpoint, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json() if resp.content else {}
        except Exception as exc:
            logger.warning("progressive_research_qianfan_failed query=%r error=%s", query[:120], exc)
            return []
        rows: list[SearchCandidate] = []
        for item in list(data.get("references") or []):
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            rows.append(
                SearchCandidate(
                    provider=self.name,
                    query=query,
                    title=str(item.get("title") or "").strip(),
                    url=url,
                    snippet=str(item.get("content") or item.get("summary") or "").strip(),
                )
            )
        return rows


class VolcArkProvider:
    name = "volc_ark"

    def __init__(self, *, api_key: str, model: str, base_url: str = "") -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url or "https://ark.cn-beijing.volces.com/api/v3/bots"

    async def search(self, query: str, *, max_results: int) -> list[SearchCandidate]:
        if not self.api_key or not self.model:
            logger.warning("progressive_research_volc_ark_skipped reason=missing_api_key_or_model")
            return []
        try:
            client = get_openai_compatible_client(
                api_key=self.api_key,
                base_url=self.base_url,
                model_name=self.model,
                streaming=False,
                intent="chat",
                stage="progressive_research_volc_ark",
                output_spec={},
            )
            completion = await client.ainvoke(
                [
                    Message(role=Role.SYSTEM, content="你是联网搜索助手。请搜索互联网并返回可核验来源。"),
                    Message(role=Role.USER, content=query),
                ],
            )
        except Exception as exc:
            logger.warning("progressive_research_volc_ark_failed query=%r error=%s", query[:120], exc)
            return []
        refs = []
        if isinstance(completion.raw_response, dict):
            refs = completion.raw_response.get("references") or []
        rows: list[SearchCandidate] = []
        for item in list(refs or [])[: max(1, min(20, int(max_results or 8)))]:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            rows.append(
                SearchCandidate(
                    provider=self.name,
                    query=query,
                    title=str(item.get("title") or "").strip(),
                    url=url,
                    snippet=str(item.get("content") or item.get("summary") or "").strip(),
                )
            )
        return rows


class ProviderRouter:
    def __init__(self, providers: list[SearchProvider] | None = None) -> None:
        self._providers = providers

    async def available_providers(self) -> list[SearchProvider]:
        if self._providers is not None:
            logger.info(
                "progressive_research_providers_injected providers=%s",
                [p.name for p in self._providers],
                extra={
                    "event": "progressive_research.providers_resolved",
                    "providers": [p.name for p in self._providers],
                    "source": "injected",
                },
            )
            return list(self._providers)

        settings = get_settings()
        providers: list[SearchProvider] = []
        request_context = get_request_context()
        main_id = str(request_context.get("main_id") or request_context.get("mainId") or "default").strip() or "default"
        configured: dict[str, Any] | None = None
        try:
            configured = await resolve_default_external_search_provider(main_id)
        except Exception as exc:
            logger.warning("progressive_research_provider_config_unavailable error=%s", exc)

        provider = str((configured or {}).get("provider") or "").strip()
        if provider == "tavily" and str((configured or {}).get("api_key") or "").strip():
            providers.append(TavilyProvider(api_key=str(configured.get("api_key") or "").strip()))
        elif provider == "serper" and str((configured or {}).get("api_key") or "").strip():
            providers.append(SerperProvider(api_key=str(configured.get("api_key") or "").strip()))
        elif provider == "serpapi" and str((configured or {}).get("api_key") or "").strip():
            providers.append(SerpApiProvider(api_key=str(configured.get("api_key") or "").strip()))
        elif provider == "baidu_qianfan" and str((configured or {}).get("api_key") or "").strip():
            providers.append(
                BaiduQianfanProvider(
                    api_key=str(configured.get("api_key") or "").strip(),
                    endpoint=str(configured.get("endpoint") or getattr(settings, "BAIDU_QIANFAN_SEARCH_URL", "") or "").strip(),
                )
            )
        elif provider == "volc_ark" and str((configured or {}).get("api_key") or "").strip():
            providers.append(
                VolcArkProvider(
                    api_key=str(configured.get("api_key") or "").strip(),
                    model=str(configured.get("model") or "").strip(),
                    base_url=str(configured.get("base_url") or "").strip(),
                )
            )

        tavily_key = str(getattr(settings, "TAVILY_API_KEY", "") or "").strip()
        if tavily_key and not any(p.name == "tavily" for p in providers):
            providers.append(TavilyProvider(api_key=tavily_key))
        serper_key = str(getattr(settings, "SERPER_API_KEY", "") or "").strip()
        if serper_key and not any(p.name == "serper" for p in providers):
            providers.append(SerperProvider(api_key=serper_key))
        serpapi_key = str(getattr(settings, "SERPAPI_API_KEY", "") or "").strip()
        if bool(getattr(settings, "SERPAPI_ENABLED", False)) and serpapi_key and not any(p.name == "serpapi" for p in providers):
            providers.append(SerpApiProvider(api_key=serpapi_key))
        logger.info(
            "progressive_research_providers_resolved providers=%s configured_provider=%s",
            [p.name for p in providers],
            provider,
            extra={
                "event": "progressive_research.providers_resolved",
                "providers": [p.name for p in providers],
                "configured_provider": provider,
                "has_admin_config": bool(configured),
                "source": "runtime_config",
            },
        )
        return providers

    async def search(self, queries: list[str], *, max_results_per_query: int) -> tuple[list[SearchCandidate], list[dict[str, Any]]]:
        providers = await self.available_providers()
        if not providers:
            logger.warning(
                "progressive_research_search_skipped reason=no_provider queries=%s",
                queries,
                extra={"event": "progressive_research.provider_search_skipped", "reason": "no_provider", "queries": queries},
            )
            return [], [{"event": "no_provider"}]
        trace: list[dict[str, Any]] = []
        seen: set[str] = set()
        candidates: list[SearchCandidate] = []
        for query in queries:
            for provider in providers:
                rows = await provider.search(query, max_results=max_results_per_query)
                trace.append({"provider": provider.name, "query": query, "hits": len(rows)})
                logger.info(
                    "progressive_research_provider_result provider=%s query=%r hits=%s",
                    provider.name,
                    query[:160],
                    len(rows),
                    extra={
                        "event": "progressive_research.provider_result",
                        "provider": provider.name,
                        "query": query,
                        "hits": len(rows),
                    },
                )
                for row in rows:
                    key = (row.url or f"{row.provider}:{row.title}:{row.snippet[:80]}").strip().lower()
                    if not key or key in seen:
                        continue
                    seen.add(key)
                    candidates.append(row)
        logger.info(
            "progressive_research_provider_search_finished queries=%s candidates=%s trace=%s",
            len(queries),
            len(candidates),
            trace,
            extra={
                "event": "progressive_research.provider_search_finished",
                "query_count": len(queries),
                "candidate_count": len(candidates),
                "trace": trace,
            },
        )
        return candidates, trace
