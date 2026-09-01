"""URL resource collection used by the DSH enterprise capability adapter.

The production order is intentionally stable: fetch ordinary HTTP(S) resources
directly, then use Firecrawl only for blocked, JavaScript-only, or empty pages.
"""

from __future__ import annotations

import mimetypes
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

import httpx

from app.services.firecrawl_collector import FirecrawlCollector
from app.services.page_collection_config import resolve_firecrawl_api_key
from app.utils.object_storage import ObjectStorageClient

from .url_resource_types import (
    detect_resource_format,
    filename_from_url_or_headers,
    html_title,
    html_to_text,
    is_html_response,
    looks_like_file_response,
    normalize_http_urls,
)


ApiKeyResolver = Callable[[str], Awaitable[str]]


class UrlResourceCollector:
    """Collect explicit URLs without making Firecrawl a required dependency."""

    def __init__(
        self,
        *,
        api_key_resolver: ApiKeyResolver = resolve_firecrawl_api_key,
        firecrawl_factory: Callable[[str], FirecrawlCollector] | None = None,
        storage_factory: Callable[[], ObjectStorageClient] = ObjectStorageClient,
        http_client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._api_key_resolver = api_key_resolver
        self._firecrawl_factory = firecrawl_factory or (lambda key: FirecrawlCollector(api_key=key))
        self._storage_factory = storage_factory
        self._http_client_factory = http_client_factory or (
            lambda: httpx.AsyncClient(timeout=45.0, follow_redirects=True)
        )

    async def collect(self, *, urls: list[str], tenant_id: str, user_id: str) -> dict[str, Any]:
        requested_urls = normalize_http_urls(urls)
        if not requested_urls:
            return self._failure_result([], [{
                "url": "",
                "stage": "validation",
                "error": "未找到有效的 HTTP(S) URL",
            }])

        pages: list[dict[str, Any]] = []
        downloaded_files: list[dict[str, Any]] = []
        images: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []
        fallback_urls: list[str] = []
        uploader: ObjectStorageClient | None = None

        async with self._http_client_factory() as client:
            for url in requested_urls:
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                    content = bytes(response.content or b"")
                    content_type = str(
                        response.headers.get("content-type")
                        or mimetypes.guess_type(urlparse(url).path)[0]
                        or ""
                    ).strip()
                    filename = filename_from_url_or_headers(
                        url, dict(response.headers), content_type
                    )
                    if is_html_response(content_type, content, url):
                        html = content.decode(response.encoding or "utf-8", errors="replace")
                        text = html_to_text(html)
                        if text:
                            pages.append(self._page(
                                url=url,
                                title=html_title(html) or filename or url,
                                content=text,
                                collector="direct_http",
                                content_type=content_type,
                                status_code=response.status_code,
                            ))
                        if not text or len(text) < 200:
                            fallback_urls.append(url)
                        continue
                    if looks_like_file_response(content_type, filename, content, url):
                        uploader = uploader or self._storage_factory()
                        signed_url, object_path = uploader.upload_bytes_with_path(
                            content=content,
                            user_id=user_id or "anonymous",
                            file_name=filename,
                            content_type=content_type or "application/octet-stream",
                        )
                        item = {
                            "filename": filename,
                            "url": signed_url,
                            "signed_url": signed_url,
                            "source_url": url,
                            "object_path": object_path,
                            "content_type": content_type
                            or mimetypes.guess_type(filename)[0]
                            or "application/octet-stream",
                            "detected_format": detect_resource_format(
                                content_type, filename, content, url
                            ),
                            "size": len(content),
                            "source": "direct_url_download",
                        }
                        if str(item["content_type"]).lower().startswith("image/") or filename.lower().endswith(
                            (".png", ".jpg", ".jpeg", ".webp", ".gif")
                        ):
                            images.append(item)
                        else:
                            downloaded_files.append(item)
                        continue

                    text = content.decode(response.encoding or "utf-8", errors="replace").strip()
                    if text:
                        pages.append(self._page(
                            url=url,
                            title=filename or url,
                            content=text,
                            collector="direct_http_text",
                            content_type=content_type,
                            status_code=response.status_code,
                        ))
                    else:
                        fallback_urls.append(url)
                except Exception as exc:
                    failures.append({
                        "url": url,
                        "stage": "direct_http",
                        "error": f"{type(exc).__name__}: {exc}",
                    })
                    fallback_urls.append(url)

        firecrawl_pages = await self._collect_fallback(
            urls=list(dict.fromkeys(fallback_urls)),
            tenant_id=tenant_id,
            failures=failures,
        )
        pages.extend(firecrawl_pages)
        success = bool(pages or downloaded_files or images)
        result = {
            "success": success,
            "ok": success,
            "tool": "firecrawl_collect_url",
            "resource_fetcher": "direct_http_with_firecrawl_fallback",
            "urls": requested_urls,
            "results": pages,
            "pages": pages,
            "source_material": pages,
            "collected_pages": firecrawl_pages,
            "downloaded_files": downloaded_files,
            "images": images,
            "attachments": downloaded_files,
            "failures": failures,
            "resource_bundle": {
                "requested_types": ["urls", "attachments", "images"],
                "urls": [{"url": url, "source": "user_or_upstream_text"} for url in requested_urls],
                "attachments": downloaded_files,
                "images": images,
                "resource_counts": {
                    "urls": len(requested_urls),
                    "attachments": len(downloaded_files),
                    "images": len(images),
                },
                "source": "web.collect_url",
            },
        }
        if not success:
            result["message"] = self._failure_message(failures)
        return result

    async def _collect_fallback(
        self,
        *,
        urls: list[str],
        tenant_id: str,
        failures: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        if not urls:
            return []
        try:
            api_key = await self._api_key_resolver(tenant_id)
        except Exception as exc:
            failures.extend({
                "url": url,
                "stage": "firecrawl_config",
                "error": f"Firecrawl 配置不可用，已跳过动态页面兜底: {type(exc).__name__}: {exc}",
            } for url in urls)
            return []
        if not api_key:
            failures.extend({
                "url": url,
                "stage": "firecrawl",
                "error": "Firecrawl 未配置，已跳过动态页面兜底",
            } for url in urls)
            return []
        collector = self._firecrawl_factory(api_key)
        pages: list[dict[str, Any]] = []
        for url in urls:
            try:
                page = await collector.scrape(url)
                markdown = str(page.get("markdown") or "").strip()
                if markdown:
                    pages.append({
                        "title": str(page.get("title") or url),
                        "url": str(page.get("url") or url),
                        "source": str(page.get("url") or url),
                        "content": markdown,
                        "markdown": markdown,
                        "meta": {
                            "collector": "firecrawl",
                            "metadata": page.get("metadata")
                            if isinstance(page.get("metadata"), dict) else {},
                        },
                    })
            except Exception as exc:
                failures.append({
                    "url": url,
                    "stage": "firecrawl",
                    "error": f"{type(exc).__name__}: {exc}",
                })
        return pages

    @staticmethod
    def public_result(result: dict[str, Any]) -> dict[str, Any]:
        """Remove transient signed URLs and provider raw payloads from DSH output."""

        def public_artifact(item: Any) -> dict[str, Any]:
            row = dict(item) if isinstance(item, dict) else {}
            row.pop("url", None)
            row.pop("signed_url", None)
            return row

        public = dict(result)
        files = [public_artifact(item) for item in list(result.get("downloaded_files") or [])]
        images = [public_artifact(item) for item in list(result.get("images") or [])]
        public["downloaded_files"] = files
        public["attachments"] = files
        public["images"] = images
        bundle = dict(result.get("resource_bundle") or {})
        bundle["attachments"] = files
        bundle["images"] = images
        public["resource_bundle"] = bundle
        return public

    @staticmethod
    def _page(
        *, url: str, title: str, content: str, collector: str,
        content_type: str, status_code: int,
    ) -> dict[str, Any]:
        return {
            "title": title,
            "url": url,
            "source": url,
            "content": content,
            "markdown": content,
            "meta": {
                "collector": collector,
                "content_type": content_type,
                "status_code": status_code,
            },
        }

    @staticmethod
    def _failure_result(urls: list[str], failures: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "success": False,
            "ok": False,
            "urls": urls,
            "results": [],
            "pages": [],
            "source_material": [],
            "downloaded_files": [],
            "attachments": [],
            "images": [],
            "failures": failures,
            "message": UrlResourceCollector._failure_message(failures),
        }

    @staticmethod
    def _failure_message(failures: list[dict[str, str]]) -> str:
        details = "; ".join(
            f"{item.get('url') or 'URL'} [{item.get('stage') or 'collect'}]: {item.get('error') or 'unknown error'}"
            for item in failures[:5]
        )
        return f"URL collection failed: {details}" if details else "URL collection failed"

__all__ = ["UrlResourceCollector"]
