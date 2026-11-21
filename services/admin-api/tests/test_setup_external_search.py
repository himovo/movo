from __future__ import annotations

import pytest

from app.services.external_search_provider import ExternalSearchConfigError, normalized_config
from app.services.setup_external_search import setup_provider_catalog


def test_setup_catalog_exposes_supported_providers_without_secrets() -> None:
    providers = setup_provider_catalog()

    assert [item["id"] for item in providers] == ["deepseek", "tavily", "serper", "serpapi", "baidu_qianfan", "volc_ark", "specstream"]
    assert all("apiKey" not in item for item in providers)


def test_search_config_applies_provider_defaults() -> None:
    config = normalized_config("baidu_qianfan", api_key="secret")

    assert config["api_key"] == "secret"
    assert config["endpoint"] == "https://qianfan.baidubce.com/v2/ai_search/web_search"


@pytest.mark.parametrize(
    ("provider", "endpoint"),
    [
        ("deepseek", "https://api.deepseek.com/v1/tools/search"),
        ("serper", "https://google.serper.dev/search"),
        ("serpapi", "https://serpapi.com/search.json"),
        ("specstream", "https://api.specstream.ai/v1/web-search"),
    ],
)
def test_serp_provider_config_applies_official_endpoint(provider: str, endpoint: str) -> None:
    config = normalized_config(provider, api_key="secret")

    assert config["endpoint"] == endpoint


def test_ark_requires_bot_model() -> None:
    with pytest.raises(ExternalSearchConfigError, match="Bot Model"):
        normalized_config("volc_ark", api_key="secret")
