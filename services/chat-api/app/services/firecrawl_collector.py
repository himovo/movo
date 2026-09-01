from __future__ import annotations

import asyncio
from typing import Any, Dict

import httpx


class FirecrawlCollectorError(RuntimeError):
    pass


class FirecrawlCollector:
    """Collect page content with Firecrawl and normalize it for research artifacts."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = str(api_key or "").strip()

    async def scrape(self, url: str) -> Dict[str, Any]:
        target = str(url or "").strip()
        if not target:
            raise FirecrawlCollectorError("URL 不能为空")
        if not self.api_key:
            raise FirecrawlCollectorError("未配置页面采集 Firecrawl API Key")

        result = await self._scrape_with_sdk(target)
        if not result:
            result = await self._scrape_with_http(target)
        markdown = self._extract_markdown(result)
        if not markdown:
            raise FirecrawlCollectorError("Firecrawl 未返回可用 Markdown")
        metadata = self._extract_metadata(result)
        return {
            "url": target,
            "title": str(metadata.get("title") or target).strip(),
            "markdown": markdown,
            "metadata": metadata,
            "raw": result,
        }

    async def _scrape_with_sdk(self, url: str) -> Any:
        try:
            from firecrawl import Firecrawl  # type: ignore
        except Exception:
            return None

        def call() -> Any:
            app = Firecrawl(api_key=self.api_key)
            return app.scrape(url)

        return await asyncio.to_thread(call)

    async def _scrape_with_http(self, url: str) -> Any:
        endpoint = "https://api.firecrawl.dev/v2/scrape"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"url": url, "formats": ["markdown"]}
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _as_dict(value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            try:
                dumped = value.model_dump()
                return dumped if isinstance(dumped, dict) else {}
            except Exception:
                return {}
        if hasattr(value, "__dict__"):
            data = dict(getattr(value, "__dict__", {}) or {})
            return data
        return {}

    @classmethod
    def _extract_markdown(cls, value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        data = cls._as_dict(value)
        for key in ("markdown", "content"):
            text = str(data.get(key) or "").strip()
            if text:
                return text
        nested = data.get("data")
        if nested is not None:
            return cls._extract_markdown(nested)
        return ""

    @classmethod
    def _extract_metadata(cls, value: Any) -> Dict[str, Any]:
        data = cls._as_dict(value)
        metadata = data.get("metadata")
        if isinstance(metadata, dict):
            return dict(metadata)
        nested = data.get("data")
        if nested is not None:
            return cls._extract_metadata(nested)
        return {}
