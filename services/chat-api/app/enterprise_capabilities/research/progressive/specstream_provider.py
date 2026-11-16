"""SpecStream Search API as a MOVO public-web search source."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .models import SearchCandidate


logger = logging.getLogger(__name__)
DEFAULT_ENDPOINT = "https://api.specstream.ai/v1/web-search"


class SpecStreamProvider:
    name = "specstream"

    def __init__(self, *, api_key: str, endpoint: str = DEFAULT_ENDPOINT) -> None:
        self.api_key = api_key
        self.endpoint = endpoint or DEFAULT_ENDPOINT

    async def search(self, query: str, *, max_results: int) -> list[SearchCandidate]:
        search_query = str(query or "").strip()[:2000]
        if not search_query:
            return []
        count = max(1, min(20, int(max_results or 8)))
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
                response = await client.post(
                    self.endpoint,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json={"q": search_query, "num": count, "speed": "fast"},
                )
                response.raise_for_status()
                payload: Any = response.json()
        except httpx.HTTPStatusError as exc:
            logger.warning("specstream_search_failed status=%s", exc.response.status_code)
            return []
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("specstream_search_failed error_type=%s", type(exc).__name__)
            return []

        data = payload.get("data") if isinstance(payload, dict) else None
        sources = data.get("sources") if isinstance(data, dict) else None
        if not isinstance(sources, list):
            logger.warning("specstream_search_invalid_response")
            return []
        candidates: list[SearchCandidate] = []
        for item in sources[:count]:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            candidates.append(
                SearchCandidate(
                    provider=self.name,
                    query=query,
                    title=str(item.get("title") or "").strip(),
                    url=url,
                    snippet=str(item.get("snippet") or "").strip(),
                    score=None,
                )
            )
        return candidates
