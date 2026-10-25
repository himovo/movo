"""Admit only the speaker's uploaded images to DSH's durable attachment store."""

from __future__ import annotations

import asyncio
import base64
from typing import Any

from app.dsh_runtime.contracts import ContentBlock
from app.utils.oss_uploader import AliyunOSSUploader

_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


async def image_content_blocks(images: list[dict[str, Any]], *, user_id: str) -> list[ContentBlock]:
    if not images:
        return []
    if not user_id or len(images) > 20:
        raise ValueError("Invalid image owner or too many images")
    uploader = AliyunOSSUploader()
    content: list[ContentBlock] = []
    for image in images:
        path = str(image.get("object_path") or "").strip()
        media_type = str(image.get("content_type") or "").lower()
        if not path.startswith(f"{user_id}/") or media_type not in _IMAGE_TYPES:
            raise ValueError("Image upload does not belong to the current user or has an unsupported type")
        raw = await asyncio.to_thread(uploader.read_bytes, path)
        if not raw or len(raw) > 50 * 1024 * 1024:
            raise ValueError("Image upload is empty or too large")
        content.append(ContentBlock(type="image", data={
            "mediaType": media_type,
            "data": base64.b64encode(raw).decode("ascii"),
            "name": str(image.get("filename") or "image")[:200],
        }))
    return content
