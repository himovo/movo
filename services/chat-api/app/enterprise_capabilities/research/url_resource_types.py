"""Pure helpers for classifying and rendering remotely fetched resources."""

from __future__ import annotations

import mimetypes
import re
from typing import Any
from urllib.parse import unquote, urlparse


def normalize_http_urls(urls: list[str], *, limit: int = 10) -> list[str]:
    normalized: list[str] = []
    for raw in urls[:limit]:
        url = str(raw or "").strip()
        if urlparse(url).scheme.lower() not in {"http", "https"}:
            continue
        if url not in normalized:
            normalized.append(url)
    return normalized


def filename_from_url_or_headers(url: str, headers: dict[str, Any], content_type: str) -> str:
    disposition = str(headers.get("content-disposition") or headers.get("Content-Disposition") or "")
    match = re.search(
        r"filename\*=UTF-8''([^;]+)|filename=\"?([^\";]+)\"?",
        disposition,
        flags=re.IGNORECASE,
    )
    if match:
        filename = unquote(str(match.group(1) or match.group(2) or "").strip())
        if filename:
            return filename[:180]
    path_name = unquote(str(urlparse(url).path or "").rsplit("/", 1)[-1]).strip()
    if path_name and "." in path_name:
        return path_name[:180]
    ext = mimetypes.guess_extension(content_type.split(";", 1)[0].strip()) if content_type else ""
    return f"downloaded_resource{ext or '.bin'}"


def is_html_response(content_type: str, content: bytes, url: str) -> bool:
    ctype = str(content_type or "").lower()
    if "text/html" in ctype or "application/xhtml" in ctype:
        return True
    suffix = str(urlparse(url).path or "").lower()
    if suffix.endswith((".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return False
    head = bytes(content or b"")[:512].lstrip().lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html")


def looks_like_file_response(content_type: str, filename: str, content: bytes, url: str) -> bool:
    ctype = str(content_type or "").lower()
    name = str(filename or urlparse(url).path or "").lower()
    if any(token in ctype for token in (
        "application/pdf", "application/msword",
        "application/vnd.openxmlformats-officedocument",
        "application/vnd.ms-excel", "application/vnd.ms-powerpoint",
        "application/octet-stream",
    )):
        return True
    if ctype.startswith("image/"):
        return True
    if name.endswith((".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".csv", ".tsv", ".txt", ".md", ".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return True
    magic = bytes(content or b"")[:8]
    return magic.startswith(b"%PDF") or magic.startswith(b"PK\x03\x04")


def detect_resource_format(content_type: str, filename: str, content: bytes, url: str) -> str:
    ctype = str(content_type or "").lower()
    name = str(filename or urlparse(url).path or "").lower()
    magic = bytes(content or b"")[:8]
    checks = (
        ("pdf", "pdf" in ctype or name.endswith(".pdf") or magic.startswith(b"%PDF")),
        ("docx", "wordprocessingml.document" in ctype or name.endswith(".docx")),
        ("xlsx", "spreadsheetml.sheet" in ctype or name.endswith(".xlsx")),
        ("pptx", "presentationml.presentation" in ctype or name.endswith(".pptx")),
        ("doc", "msword" in ctype or name.endswith(".doc")),
        ("xls", "ms-excel" in ctype or name.endswith(".xls")),
        ("ppt", "ms-powerpoint" in ctype or name.endswith(".ppt")),
    )
    for resource_format, matched in checks:
        if matched:
            return resource_format
    if ctype.startswith("image/"):
        return ctype.split("/", 1)[-1].split(";", 1)[0].strip() or "image"
    for suffix, resource_format in ((".csv", "csv"), (".tsv", "tsv"), (".md", "md"), (".txt", "txt")):
        if name.endswith(suffix):
            return resource_format
    if magic.startswith(b"PK\x03\x04"):
        return "zip"
    guessed = mimetypes.guess_type(filename or urlparse(url).path)[0] or ""
    return guessed.split("/", 1)[-1].split(".", 1)[-1] if guessed else ""


def html_title(html: str) -> str:
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", str(html or ""))
    if not match:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", match.group(1))).strip()


def html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", str(html or ""))
    title = html_title(text)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</(p|div|section|article|li|tr|h[1-6])>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    if title and title not in text[:300]:
        return f"# {title}\n\n{text}".strip()
    return text


__all__ = [
    "detect_resource_format",
    "filename_from_url_or_headers",
    "html_title",
    "html_to_text",
    "is_html_response",
    "looks_like_file_response",
    "normalize_http_urls",
]
