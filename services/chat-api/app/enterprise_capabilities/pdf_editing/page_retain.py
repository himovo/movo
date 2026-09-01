from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Iterable

from pypdf import PdfReader, PdfWriter


def _resolved(value: Any) -> Any:
    try:
        return value.get_object()
    except AttributeError:
        return value


def _annotations(page: Any) -> list[Any]:
    value = _resolved(page.get("/Annots") or [])
    return list(value) if isinstance(value, (list, tuple)) else []


@dataclass(frozen=True)
class PdfPageRetainResult:
    file_bytes: bytes
    source_page_count: int
    kept_pages: tuple[int, ...]
    removed_pages: tuple[int, ...]
    warnings: tuple[str, ...]


def _normalize_keep_pages(values: Iterable[Any], *, page_count: int) -> tuple[int, ...]:
    normalized: set[int] = set()
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("keep_pages must contain only integer page numbers")
        if value < 1 or value > page_count:
            raise ValueError(f"keep_pages contains out-of-range page {value}; source has {page_count} pages")
        normalized.add(value)
    if not normalized:
        raise ValueError("keep_pages must contain at least one source page")
    return tuple(sorted(normalized))


def _page_fingerprint(page: Any) -> tuple[Any, ...]:
    contents = page.get_contents()
    content_bytes = bytes(contents.get_data()) if contents is not None else b""
    media = tuple(float(value) for value in page.mediabox)
    crop = tuple(float(value) for value in page.cropbox)
    return (
        hashlib.sha256(content_bytes).hexdigest(),
        media,
        crop,
        int(page.get("/Rotate") or 0),
        len(_annotations(page)),
    )


def _document_warnings(reader: PdfReader, *, removed_pages: tuple[int, ...]) -> tuple[str, ...]:
    warnings: list[str] = []
    root = _resolved(reader.trailer.get("/Root") or {})
    acro_form = root.get("/AcroForm") if hasattr(root, "get") else None
    if acro_form is not None:
        warnings.append("interactive_form_structure_may_not_be_preserved")
    if removed_pages:
        has_internal_links = False
        for page in reader.pages:
            for reference in _annotations(page):
                try:
                    annotation = _resolved(reference)
                    action = _resolved(annotation.get("/A") or {})
                    if annotation.get("/Dest") is not None or action.get("/S") == "/GoTo":
                        has_internal_links = True
                        break
                except Exception:
                    continue
            if has_internal_links:
                break
        if has_internal_links:
            warnings.append("internal_links_to_removed_pages_may_be_unavailable")
    return tuple(warnings)


def retain_pdf_pages(source_bytes: bytes, keep_pages: Iterable[Any]) -> PdfPageRetainResult:
    if not source_bytes:
        raise ValueError("source PDF is empty")
    try:
        reader = PdfReader(BytesIO(source_bytes), strict=False)
    except Exception as exc:
        raise ValueError("artifact is not a readable PDF") from exc
    if reader.is_encrypted:
        try:
            unlocked = bool(reader.decrypt(""))
        except Exception:
            unlocked = False
        if not unlocked:
            raise ValueError("encrypted PDF requires a password and cannot be processed")

    page_count = len(reader.pages)
    if page_count <= 0:
        raise ValueError("source PDF contains no pages")
    kept = _normalize_keep_pages(keep_pages, page_count=page_count)
    removed = tuple(page for page in range(1, page_count + 1) if page not in kept)
    source_fingerprints = [_page_fingerprint(reader.pages[page - 1]) for page in kept]

    writer = PdfWriter()
    for page in kept:
        writer.add_page(reader.pages[page - 1])
    metadata = {
        str(key): str(value)
        for key, value in dict(reader.metadata or {}).items()
        if str(key).startswith("/") and value is not None
    }
    if metadata:
        writer.add_metadata(metadata)
    output = BytesIO()
    writer.write(output)
    file_bytes = output.getvalue()

    verified = PdfReader(BytesIO(file_bytes), strict=False)
    if len(verified.pages) != len(kept):
        raise RuntimeError("derived PDF page-count verification failed")
    output_fingerprints = [_page_fingerprint(page) for page in verified.pages]
    if output_fingerprints != source_fingerprints:
        raise RuntimeError("derived PDF page-content verification failed")

    return PdfPageRetainResult(
        file_bytes=file_bytes,
        source_page_count=page_count,
        kept_pages=kept,
        removed_pages=removed,
        warnings=_document_warnings(reader, removed_pages=removed),
    )


__all__ = ["PdfPageRetainResult", "retain_pdf_pages"]
