"""Add searchable OCR chunks for text found in embedded Office images."""

from __future__ import annotations

import logging
import hashlib
import re
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

from app.services.office_image_sources import EmbeddedImage, inspect_office_images, location_title

if TYPE_CHECKING:
    from app.services.document_parsing_service import ParsedDocument


logger = logging.getLogger(__name__)
_MAX_IMAGE_PIXELS = 80_000_000
_MAX_OCR_SIDE = 3500
_MAX_CHUNK_CHARS = 850


@lru_cache(maxsize=1)
def _ocr_engine():
    from rapidocr import RapidOCR

    return RapidOCR()


def add_office_image_ocr(parsed: ParsedDocument, path: Path, ext: str) -> ParsedDocument:
    """OCR unique embedded images and append their text as normal raw chunks."""
    inventory = inspect_office_images(path)
    images = sorted(
        inventory.images,
        key=lambda image: (image.page_no is None, image.page_no or 0, image.media_path),
    )
    if not images and not inventory.unsupported_media_paths:
        return parsed
    base_text = "\n".join([parsed.markdown, *(str(item.get("text") or "") for item in parsed.raw_chunks or [])])
    known_lines = {_normalize(line) for line in base_text.splitlines() if _normalize(line)}
    chunks = list(parsed.raw_chunks or [])
    markdown_parts: list[str] = []
    recognized = 0
    unreadable: list[str] = []
    seen_images: set[str] = set()
    for image in images:
        digest = hashlib.sha256(image.data).hexdigest()
        if digest in seen_images:
            continue
        seen_images.add(digest)
        try:
            lines = _new_ocr_lines(image, known_lines)
        except Exception as exc:
            logger.warning("Office image OCR failed: part=%s error_type=%s", image.media_path, type(exc).__name__)
            unreadable.append(image.media_path)
            continue
        if not lines:
            continue
        recognized += 1
        title = location_title(image)
        for part in _split_lines(lines):
            text = "\n".join(part)
            chunk_id = f"raw_{len(chunks) + 1:06d}"
            chunks.append({
                "chunkId": chunk_id,
                "ordinal": len(chunks),
                "text": text,
                "contextualText": f"{title}\n{text}",
                "titlePath": [title],
                "pageNo": image.page_no,
                "contentType": "image",
                "chunkStage": "raw",
                "sourceChunkIds": [],
                "metadata": {
                    "parser": "rapidocr",
                    "sourceKind": "office_embedded_image_ocr",
                    "format": ext,
                    "mediaPath": image.media_path,
                    "locations": list(image.locations),
                    "sourceAnchor": {"pageNo": image.page_no} if image.page_no else {},
                },
            })
            markdown_parts.append(f"### {title}\n\n{text}")
    parsed.raw_chunks = chunks
    if markdown_parts:
        parsed.markdown = "\n\n".join([parsed.markdown, *markdown_parts]).strip()
    parsed.raw["movoOfficeImageOcr"] = {
        "embeddedImageCount": len(images),
        "recognizedImageCount": recognized,
        "unreadableImageParts": unreadable,
        "unsupportedImageParts": inventory.unsupported_media_paths,
    }
    return parsed


def _new_ocr_lines(image: EmbeddedImage, known_lines: set[str]) -> list[str]:
    import numpy as np
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        with Image.open(BytesIO(image.data)) as source:
            if source.width * source.height > _MAX_IMAGE_PIXELS:
                raise ValueError("embedded image exceeds pixel limit")
            source.draft("RGB", (_MAX_OCR_SIDE, _MAX_OCR_SIDE))
            source.thumbnail((_MAX_OCR_SIDE, _MAX_OCR_SIDE))
            picture = ImageOps.exif_transpose(source).convert("RGB")
    except (Image.DecompressionBombError, UnidentifiedImageError) as exc:
        raise ValueError("embedded image cannot be decoded") from exc
    if picture.width < 32 or picture.height < 32:
        return []
    result = _ocr_engine()(np.asarray(picture))
    texts = list(getattr(result, "txts", None) or ())
    scores = list(getattr(result, "scores", None) or ())
    fresh: list[str] = []
    local_lines: set[str] = set()
    for index, value in enumerate(texts):
        line = str(value).strip()
        score = float(scores[index]) if index < len(scores) else 0.0
        normalized = _normalize(line)
        if score < 0.7 or len(normalized) < 2 or normalized in known_lines or normalized in local_lines:
            continue
        if not re.search(r"[\w\u3400-\u9fff]", line):
            continue
        fresh.append(line)
        local_lines.add(normalized)
    return fresh


def _split_lines(lines: list[str]) -> list[list[str]]:
    parts: list[list[str]] = []
    current: list[str] = []
    length = 0
    for line in lines:
        if current and length + len(line) + 1 > _MAX_CHUNK_CHARS:
            parts.append(current)
            current = []
            length = 0
        current.append(line)
        length += len(line) + 1
    if current:
        parts.append(current)
    return parts


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold().strip()
