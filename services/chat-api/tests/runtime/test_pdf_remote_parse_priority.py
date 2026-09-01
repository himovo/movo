from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services import document_parser as document_parser_module
from app.services.document_processing_parse_client import DocumentProcessingParseClient
from app.services.document_parser import DocumentParserService


def test_pdf_parse_prefers_document_processing_service(monkeypatch) -> None:
    async def remote_parse(document, *, timeout_seconds=None):
        return {
            "ok": True,
            "markdown": "# 远程解析结果",
            "filename": "sample.pdf",
            "parser": "docling",
            "structured_content": {"parser": "docling"},
            "parse_quality": {"source": "document_processing"},
        }

    async def local_object_path(*, object_path, filename):
        raise AssertionError("local parser should not run when remote parser succeeds")

    service = DocumentParserService()
    monkeypatch.setattr(document_parser_module.document_processing_parse_client, "parse_markdown", remote_parse)
    monkeypatch.setattr(service, "_local_parse_object_path", local_object_path)

    result = asyncio.run(
        service.parse_document(
            document={
                "filename": "sample.pdf",
                "content_type": "application/pdf",
                "object_path": "uploads/sample.pdf",
                "signed_url": "https://storage.example.com/sample.pdf",
            }
        )
    )

    assert result["ok"] is True
    assert result["parser"] == "docling"
    assert result["markdown"] == "# 远程解析结果"


def test_pdf_parse_falls_back_to_local_when_document_processing_fails(monkeypatch) -> None:
    async def remote_parse(document, *, timeout_seconds=None):
        return {
            "ok": False,
            "error": "document_processing_unavailable",
            "filename": "sample.pdf",
            "parser": "document_processing",
        }

    async def local_object_path(*, object_path, filename):
        return {
            "ok": True,
            "markdown": "# 本地解析结果",
            "filename": filename,
            "parser": "local_pdf_structured",
        }

    service = DocumentParserService()
    monkeypatch.setattr(document_parser_module.document_processing_parse_client, "parse_markdown", remote_parse)
    monkeypatch.setattr(service, "_local_parse_object_path", local_object_path)

    result = asyncio.run(
        service.parse_document(
            document={
                "filename": "sample.pdf",
                "content_type": "application/pdf",
                "object_path": "uploads/sample.pdf",
                "signed_url": "https://storage.example.com/sample.pdf",
            }
        )
    )

    assert result["ok"] is True
    assert result["parser"] == "local_pdf_structured"
    assert result["markdown"] == "# 本地解析结果"


def test_document_processing_client_sends_internal_url_for_local_storage(monkeypatch) -> None:
    client = DocumentProcessingParseClient()
    monkeypatch.setattr(client._settings, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(client._settings, "BACKEND_INTERNAL_BASE_URL", "http://127.0.0.1:8000")
    monkeypatch.setattr(client._settings, "LOCAL_STORAGE_PATH", "storage")
    monkeypatch.setattr(client._settings, "FILE_PUBLIC_PATH_PREFIX", "/askai-api/api/files")

    source = client._source_from_document(
        {
            "filename": "sample.pdf",
            "content_type": "application/pdf",
            "object_path": "user/2026/sample.pdf",
        }
    )

    assert source["storageType"] == "local"
    source_url = client._source_url_from_document({}, source)
    assert source_url.startswith("http://127.0.0.1:8000/api/files/user/2026/sample.pdf?")
    assert "expires=" in source_url
    assert "signature=" in source_url
