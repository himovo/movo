from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from app.domain.jobs import ParseMarkdownRequest
from app.integrations.storage import get_storage_adapter
from app.services.document_parsing_service import (
    _rag_chunk_options,
    build_rag_chunks,
    chunk_markdown,
    parse_document,
)


def _copy_source_to_path(request: ParseMarkdownRequest, source_path: Path) -> None:
    source_url = str(request.sourceUrl or "").strip()
    if source_url.startswith(("http://", "https://")):
        http_request = Request(source_url, headers={"User-Agent": "MOVO-DocumentParser/1.0"})
        with urlopen(http_request, timeout=60) as response, source_path.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
        return

    source_storage = get_storage_adapter(request.source.storageType)
    with source_storage.open_file(request.source.storageKey) as source, source_path.open("wb") as output:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)


def parse_markdown_sync(request: ParseMarkdownRequest) -> dict[str, Any]:
    """Parse one stored document synchronously for runtime graph usage."""

    with tempfile.TemporaryDirectory(prefix="askai-sync-parse-") as temp_dir:
        temp_path = Path(temp_dir)
        suffix = Path(request.source.filename or request.source.storageKey).suffix or ".document"
        source_path = temp_path / f"source{suffix}"
        _copy_source_to_path(request, source_path)

        parsed = parse_document(source_path, request.source.filename or request.source.storageKey)

    raw_chunks = parsed.raw_chunks if parsed.raw_chunks is not None else chunk_markdown(
        parsed.markdown,
        request.chunkSize,
        request.chunkOverlap,
    )
    rag_chunks = parsed.rag_chunks if parsed.rag_chunks is not None else build_rag_chunks(
        raw_chunks,
        _rag_chunk_options(request.minChunkSize, request.chunkSize, request.chunkOverlap),
    )
    raw = dict(parsed.raw or {})
    parser = str(raw.get("parser") or "docling").strip()
    return {
        "markdown": parsed.markdown,
        "raw": raw,
        "rawChunks": raw_chunks,
        "ragChunks": rag_chunks,
        "parser": parser,
        "markdownChars": len(parsed.markdown or ""),
    }
