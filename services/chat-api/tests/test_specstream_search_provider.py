from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from app.enterprise_capabilities.research.progressive import specstream_provider as module
from app.enterprise_capabilities.research.progressive.provider_router import ProviderRouter
from app.services import search_provider_config


def test_search_uses_specstream_api_and_normalizes_sources() -> None:
    asyncio.run(_verify_search())


async def _verify_search() -> None:
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": {
                    "sources": [
                        {
                            "title": "Example",
                            "url": "https://example.com/a",
                            "snippet": "Example snippet",
                        },
                        {
                            "title": "No URL",
                            "snippet": "Skip",
                        },
                    ]
                }
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    with patch.object(module.httpx, "AsyncClient", return_value=client):
        rows = await module.SpecStreamProvider(api_key="example-secret").search("MOVO", max_results=3)

    assert len(rows) == 1
    assert rows[0].provider == "specstream"
    assert rows[0].title == "Example"
    assert rows[0].url == "https://example.com/a"
    assert rows[0].snippet == "Example snippet"
    assert rows[0].score is None
    assert requests[0].url == module.DEFAULT_ENDPOINT
    assert requests[0].headers["authorization"] == "Bearer example-secret"
    assert requests[0].headers["accept"] == "application/json"
    assert json.loads(requests[0].content) == {"q": "MOVO", "num": 3, "speed": "fast"}


def test_search_handles_http_error_and_empty_query() -> None:
    asyncio.run(_verify_error_and_empty())


async def _verify_error_and_empty() -> None:
    def respond_error(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"code": "invalid_token", "message": "Invalid key"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond_error))
    with patch.object(module.httpx, "AsyncClient", return_value=client):
        rows = await module.SpecStreamProvider(api_key="bad-secret").search("MOVO", max_results=3)
    assert rows == []

    assert await module.SpecStreamProvider(api_key="example-secret").search("   ", max_results=3) == []


def test_specstream_config_and_router_resolution() -> None:
    asyncio.run(_verify_config_and_routing())


async def _verify_config_and_routing() -> None:
    class Cursor:
        async def to_list(self, *, length):
            assert length == len(search_provider_config.SUPPORTED_PROVIDERS)
            return [{"provider": "specstream", "config": {"api_key_encrypted": "cipher", "endpoint": module.DEFAULT_ENDPOINT}}]

    class Collection:
        async def find_one(self, query, *args, **kwargs):
            return None

        def find(self, query):
            assert query["main_id"] == "tenant"
            assert query["enabled"] is True
            return Cursor()

    class Database:
        def __getitem__(self, name):
            assert name == search_provider_config.COLLECTION
            return Collection()

    with patch.object(search_provider_config, "get_db", return_value=Database()), patch.object(
        search_provider_config, "decrypt_secret", return_value="tenant-key"
    ):
        config = await search_provider_config.resolve_default_external_search_provider("tenant")
    assert config is not None
    assert config["provider"] == "specstream"
    assert config["endpoint"] == module.DEFAULT_ENDPOINT

    configured = {"provider": "specstream", "api_key": "tenant-key", "endpoint": module.DEFAULT_ENDPOINT}
    settings = SimpleNamespace(TAVILY_API_KEY="host-key", SERPER_API_KEY="", SERPAPI_API_KEY="", SERPAPI_ENABLED=False)
    with (
        patch("app.enterprise_capabilities.research.progressive.provider_router.get_settings", return_value=settings),
        patch("app.enterprise_capabilities.research.progressive.provider_router.get_request_context", return_value={"main_id": "tenant"}),
        patch("app.enterprise_capabilities.research.progressive.provider_router.resolve_default_external_search_provider", new=AsyncMock(return_value=configured)),
        patch("app.enterprise_capabilities.research.progressive.provider_router.has_saved_external_search_config", new=AsyncMock(return_value=True)),
    ):
        providers = await ProviderRouter().available_providers()
    assert [provider.name for provider in providers] == ["specstream"]

    with (
        patch("app.enterprise_capabilities.research.progressive.provider_router.get_settings", return_value=settings),
        patch("app.enterprise_capabilities.research.progressive.provider_router.get_request_context", return_value={"main_id": "tenant"}),
        patch("app.enterprise_capabilities.research.progressive.provider_router.resolve_default_external_search_provider", new=AsyncMock(return_value=None)),
        patch("app.enterprise_capabilities.research.progressive.provider_router.has_saved_external_search_config", new=AsyncMock(return_value=True)),
    ):
        providers = await ProviderRouter().available_providers()
    assert providers == []
