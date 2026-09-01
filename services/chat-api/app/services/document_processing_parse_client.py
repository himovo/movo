from __future__ import annotations

import logging
from typing import Any, Dict

import httpx

from app.core.config import get_settings
from app.utils.oss_uploader import ObjectStorageClient


logger = logging.getLogger(__name__)


class DocumentProcessingParseClient:
    """Small client for the document-processing synchronous parse endpoint."""

    def __init__(self) -> None:
        self._settings = get_settings()

    def _source_from_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        storage_key = str(document.get("object_path") or document.get("storage_key") or "").strip()
        if not storage_key:
            return {}
        return {
            "storageType": str(document.get("storage_type") or self._settings.STORAGE_BACKEND or "oss").strip() or "oss",
            "storageBucket": str(document.get("storage_bucket") or self._settings.OSS_BUCKET_NAME or "").strip(),
            "storageKey": storage_key,
            "filename": str(document.get("filename") or "document").strip() or "document",
            "mimeType": str(document.get("content_type") or document.get("mime_type") or "").strip(),
        }

    def _source_url_from_document(self, document: Dict[str, Any], source: Dict[str, Any]) -> str:
        storage_type = str(source.get("storageType") or "").strip().lower()
        storage_key = str(source.get("storageKey") or "").strip()
        if storage_type == "local" and storage_key:
            try:
                return str(ObjectStorageClient().internal_url(storage_key) or "").strip()
            except Exception:
                return ""
        return ""

    async def parse_markdown(self, document: Dict[str, Any], *, timeout_seconds: float | None = None) -> Dict[str, Any]:
        base_url = str(getattr(self._settings, "DOCUMENT_PROCESSING_BASE_URL", "") or "").strip().rstrip("/")
        token = str(getattr(self._settings, "DOCUMENT_PROCESSING_SERVICE_TOKEN", "") or "").strip()
        source = self._source_from_document(document)
        filename = str(document.get("filename") or source.get("filename") or "document").strip()
        if not base_url or not token or not source:
            return {}
        payload = {"source": source}
        source_url = self._source_url_from_document(document, source)
        if source_url:
            payload["sourceUrl"] = source_url
        configured_timeout = float(getattr(self._settings, "DOCUMENT_PROCESSING_SYNC_PARSE_TIMEOUT_SECONDS", 180.0) or 180.0)
        timeout = max(float(timeout_seconds or 0.0), configured_timeout)
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                resp = await client.post(
                    f"{base_url}/api/documents/parse-markdown",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                    },
                )
            if resp.status_code >= 400:
                logger.info(
                    "document_processing_parse_failed filename=%s status=%s body=%s",
                    filename[:120],
                    resp.status_code,
                    str(resp.text or "")[:300],
                )
                return {
                    "ok": False,
                    "error": f"document_processing_http_{resp.status_code}",
                    "parser": "document_processing",
                    "filename": filename,
                    "source_url": f"object://{source.get('storageKey')}",
                }
            data = resp.json() if str(resp.text or "").strip() else {}
        except Exception as exc:
            logger.info("document_processing_parse_unavailable filename=%s error=%s", filename[:120], str(exc)[:300])
            return {
                "ok": False,
                "error": f"document_processing_unavailable: {exc}",
                "parser": "document_processing",
                "filename": filename,
                "source_url": f"object://{source.get('storageKey')}",
            }

        markdown = str((data or {}).get("markdown") or "").strip()
        return {
            "ok": bool(markdown),
            "error": "" if markdown else "document_processing_missing_markdown",
            "markdown": markdown,
            "structured_content": dict((data or {}).get("raw") or {}),
            "parse_quality": {
                "source": "document_processing",
                "markdown_chars": int((data or {}).get("markdownChars") or len(markdown)),
                "raw_chunk_count": len(list((data or {}).get("rawChunks") or [])),
                "rag_chunk_count": len(list((data or {}).get("ragChunks") or [])),
            },
            "raw_chunks": list((data or {}).get("rawChunks") or []),
            "rag_chunks": list((data or {}).get("ragChunks") or []),
            "source_url": f"object://{source.get('storageKey')}",
            "filename": filename,
            "parser": str((data or {}).get("parser") or "document_processing").strip() or "document_processing",
        }


document_processing_parse_client = DocumentProcessingParseClient()
