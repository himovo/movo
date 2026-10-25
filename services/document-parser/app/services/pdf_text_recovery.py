"""Compare PDF native text with Docling output and recover dropped pages."""

from __future__ import annotations

import logging
import re
from collections import Counter
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


def supplement_pdf_chunks(path: Path, chunks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from pypdf import PdfReader

    pages = PdfReader(str(path)).pages
    report: list[dict[str, Any]] = []
    for page_no, page in enumerate(pages, start=1):
        try:
            native_text = (page.extract_text() or "").strip()
        except Exception:
            native_text = ""
        native_chars = _characters(native_text)
        page_chunks = [item for item in chunks if item.get("pageNo") == page_no]
        parsed_text = "\n".join(str(item.get("text") or "") for item in page_chunks)
        coverage = _coverage(native_chars, _characters(parsed_text))
        native_missing = _missing_lines(native_text, parsed_text)
        ocr_missing: list[str] = []
        ocr_attempted = False
        ocr_failed = False
        try:
            has_images = bool(page.images)
        except Exception:
            has_images = False
        if has_images:
            ocr_attempted = True
            try:
                from app.services.pdf_page_ocr import extract_page_ocr_text

                ocr_text = extract_page_ocr_text(path, page_no)
                ocr_missing = _missing_lines(ocr_text, "\n".join([native_text, parsed_text]))
            except Exception:
                ocr_failed = True
                logger.exception("PDF page OCR failed for page %s", page_no)
        missing_lines = list(dict.fromkeys([*native_missing, *ocr_missing]))
        missing_chars = sum(_characters(line).total() for line in missing_lines)
        recovered = bool(missing_lines)
        recovery_text = "\n".join(missing_lines) if recovered else ""
        if recovered:
            ordinal = len(chunks)
            chunks.append({
                "chunkId": f"raw_{ordinal + 1:06d}", "ordinal": ordinal,
                "text": recovery_text, "contextualText": recovery_text,
                "titlePath": [f"第 {page_no} 页"], "pageNo": page_no,
                "contentType": "text", "chunkStage": "raw", "sourceChunkIds": [],
                "metadata": {"parser": "pypdf", "sourceKind": "native_text_recovery", "sourceAnchor": {"pageNo": page_no}},
            })
        report.append({
            "pageNo": page_no, "nativeChars": native_chars.total(),
            "parsedChars": _characters(parsed_text).total(),
            "nativeCoverage": round(coverage, 3),
            "finalNativeCoverage": round(_coverage(native_chars, _characters("\n".join([parsed_text, recovery_text]))), 3),
            "nativeTextRecovered": recovered and bool(native_missing),
            "ocrTextRecovered": recovered and bool(ocr_missing),
            "missingNativeChars": missing_chars,
            "ocrAttempted": ocr_attempted, "ocrFailed": ocr_failed,
            "needsReview": (not page_chunks and not recovered) or ocr_failed,
        })
    return chunks, {
        "pageCount": len(pages), "pages": report,
        "recoveredPages": [item["pageNo"] for item in report if item["nativeTextRecovered"]],
        "reviewPages": [item["pageNo"] for item in report if item["needsReview"]],
    }


def _characters(text: str) -> Counter[str]:
    return Counter(re.findall(r"[\w\u3400-\u9fff]", text.lower()))


def _trigrams(text: str) -> Counter[str]:
    normalized = "".join(re.findall(r"[\w\u3400-\u9fff]", text.lower()))
    return Counter(normalized[index:index + 3] for index in range(max(0, len(normalized) - 2)))


def _coverage(expected: Counter[str], actual: Counter[str]) -> float:
    total = expected.total()
    return sum((expected & actual).values()) / total if total else 1.0


def _missing_lines(native_text: str, parsed_text: str) -> list[str]:
    available = _trigrams(parsed_text)
    missing = []
    for line in native_text.splitlines():
        line = line.strip()
        grams = _trigrams(line)
        if not grams:
            if _characters(line).total() and line not in parsed_text:
                missing.append(line)
            continue
        if _coverage(grams, available) < 0.8:
            missing.append(line)
        else:
            available.subtract(grams)
    return missing
