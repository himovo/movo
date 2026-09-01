from __future__ import annotations

import asyncio

from app.enterprise_capabilities.research import UrlResourceCollector


class _Response:
    def __init__(self, content: bytes, content_type: str, *, status_code: int = 200) -> None:
        self.content = content
        self.headers = {"content-type": content_type}
        self.status_code = status_code
        self.encoding = "utf-8"

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _Client:
    def __init__(self, responses: dict[str, _Response | Exception]) -> None:
        self.responses = responses

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get(self, url: str):
        value = self.responses[url]
        if isinstance(value, Exception):
            raise value
        return value


class _Storage:
    def upload_bytes_with_path(self, *, content, user_id, file_name, content_type):
        assert content and user_id == "user-a" and file_name == "guide.pdf"
        assert content_type == "application/pdf"
        return "https://signed.invalid/guide.pdf", "user-a/files/guide.pdf"


class _Firecrawl:
    async def scrape(self, url: str):
        return {
            "url": url,
            "title": "动态页面",
            "markdown": "Firecrawl rendered content",
            "metadata": {"language": "zh"},
        }


def _collector(responses, *, api_key="", firecrawl_factory=None, storage_factory=_Storage):
    async def resolve(_tenant_id: str) -> str:
        return api_key

    return UrlResourceCollector(
        api_key_resolver=resolve,
        firecrawl_factory=firecrawl_factory,
        storage_factory=storage_factory,
        http_client_factory=lambda: _Client(responses),
    )


def test_direct_html_collection_works_without_firecrawl_key() -> None:
    body = ("<html><head><title>AskBot</title></head><body>" + "企业智能体平台 " * 40 + "</body></html>").encode()
    result = asyncio.run(_collector({
        "https://example.test/": _Response(body, "text/html; charset=utf-8"),
    }).collect(urls=["https://example.test/"], tenant_id="tenant-a", user_id="user-a"))

    assert result["success"] is True
    assert result["results"][0]["meta"]["collector"] == "direct_http"
    assert result["results"][0]["title"] == "AskBot"
    assert "AskBot" in result["results"][0]["content"]
    assert result["failures"] == []


def test_remote_file_is_downloaded_without_firecrawl_and_public_result_hides_signature() -> None:
    result = asyncio.run(_collector({
        "https://example.test/guide.pdf": _Response(b"%PDF-1.7 content", "application/pdf"),
    }).collect(urls=["https://example.test/guide.pdf"], tenant_id="tenant-a", user_id="user-a"))

    assert result["success"] is True
    assert result["downloaded_files"][0]["detected_format"] == "pdf"
    assert result["downloaded_files"][0]["object_path"] == "user-a/files/guide.pdf"
    public = UrlResourceCollector.public_result(result)
    assert "signed_url" not in public["downloaded_files"][0]
    assert "url" not in public["downloaded_files"][0]


def test_firecrawl_is_used_only_after_direct_collection_fails() -> None:
    result = asyncio.run(_collector(
        {"https://dynamic.test/": RuntimeError("blocked")},
        api_key="configured",
        firecrawl_factory=lambda _key: _Firecrawl(),
    ).collect(urls=["https://dynamic.test/"], tenant_id="tenant-a", user_id="user-a"))

    assert result["success"] is True
    assert result["results"][0]["meta"]["collector"] == "firecrawl"
    assert result["failures"][0]["stage"] == "direct_http"


def test_partial_success_stays_successful_and_preserves_failure_details_without_firecrawl() -> None:
    body = ("<html><body>" + "available " * 40 + "</body></html>").encode()
    result = asyncio.run(_collector({
        "https://ok.test/": _Response(body, "text/html"),
        "https://blocked.test/": RuntimeError("connection refused"),
    }).collect(
        urls=["https://ok.test/", "https://blocked.test/"],
        tenant_id="tenant-a",
        user_id="user-a",
    ))

    assert result["success"] is True
    assert len(result["results"]) == 1
    assert any(item["stage"] == "firecrawl" for item in result["failures"])


def test_total_failure_reports_direct_and_optional_fallback_reasons() -> None:
    result = asyncio.run(_collector({
        "https://blocked.test/": RuntimeError("connection refused"),
    }).collect(urls=["https://blocked.test/"], tenant_id="tenant-a", user_id="user-a"))

    assert result["success"] is False
    assert result["ok"] is False
    assert "connection refused" in result["message"]
    assert "Firecrawl 未配置" in result["message"]


def test_firecrawl_configuration_failure_does_not_discard_direct_page() -> None:
    async def unavailable(_tenant_id: str) -> str:
        raise RuntimeError("configuration store unavailable")

    body = b"<html><head><title>Short</title></head><body>useful result</body></html>"
    collector = UrlResourceCollector(
        api_key_resolver=unavailable,
        http_client_factory=lambda: _Client({
            "https://short.test/": _Response(body, "text/html"),
        }),
    )
    result = asyncio.run(collector.collect(
        urls=["https://short.test/"], tenant_id="tenant-a", user_id="user-a"
    ))

    assert result["success"] is True
    assert result["results"][0]["title"] == "Short"
    assert result["failures"][0]["stage"] == "firecrawl_config"
