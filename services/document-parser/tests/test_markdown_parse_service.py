from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.domain.jobs import ParseMarkdownRequest
from app.services import markdown_parse_service
from app.services.document_parsing_service import ParsedDocument


class _FakeStorage:
    def open_file(self, storage_key: str):
        assert storage_key == "uploads/sample.pdf"
        return BytesIO(b"%PDF-1.4 fake")


def test_parse_markdown_sync_uses_existing_parser_and_returns_markdown(monkeypatch) -> None:
    monkeypatch.setattr(markdown_parse_service, "get_storage_adapter", lambda storage_type: _FakeStorage())
    monkeypatch.setattr(
        markdown_parse_service,
        "parse_document",
        lambda path, filename: ParsedDocument(
            markdown="# 标题\n\n| 地区 | 行业 |\n|---|---|\n| 北京 | 软件 |",
            raw={"parser": "docling", "tables": [{"rows": 2}]},
            raw_chunks=[{"text": "北京 软件"}],
            rag_chunks=[{"text": "北京 软件", "chunkStage": "rag"}],
        ),
    )

    result = markdown_parse_service.parse_markdown_sync(
        ParseMarkdownRequest(
            source={
                "storageType": "oss",
                "storageKey": "uploads/sample.pdf",
                "filename": "sample.pdf",
                "mimeType": "application/pdf",
            }
        )
    )

    assert result["parser"] == "docling"
    assert "北京" in result["markdown"]
    assert result["markdownChars"] == len(result["markdown"])
    assert len(result["rawChunks"]) == 1
    assert len(result["ragChunks"]) == 1


def test_parse_markdown_sync_can_read_source_url_without_storage(monkeypatch) -> None:
    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self, _size: int):
            if getattr(self, "_done", False):
                return b""
            self._done = True
            return b"%PDF-1.4 fake from url"

    def fake_urlopen(request, timeout):
        assert request.full_url == "http://127.0.0.1:8000/api/files/uploads/sample.pdf"
        assert timeout == 60
        return _FakeResponse()

    def fail_storage(_storage_type):
        raise AssertionError("storage adapter should not be used when sourceUrl is provided")

    monkeypatch.setattr(markdown_parse_service, "urlopen", fake_urlopen)
    monkeypatch.setattr(markdown_parse_service, "get_storage_adapter", fail_storage)
    monkeypatch.setattr(
        markdown_parse_service,
        "parse_document",
        lambda path, filename: ParsedDocument(markdown="从 URL 解析", raw={"parser": "docling"}),
    )

    result = markdown_parse_service.parse_markdown_sync(
        ParseMarkdownRequest(
            source={
                "storageType": "local",
                "storageKey": "uploads/sample.pdf",
                "filename": "sample.pdf",
                "mimeType": "application/pdf",
            },
            sourceUrl="http://127.0.0.1:8000/api/files/uploads/sample.pdf",
        )
    )

    assert result["markdown"] == "从 URL 解析"
