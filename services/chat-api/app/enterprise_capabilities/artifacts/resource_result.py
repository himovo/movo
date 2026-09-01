"""Stable cross-tool contract for resources derived from owned documents."""

from __future__ import annotations

import mimetypes
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.enterprise_capabilities.artifacts.references import (
    require_owned_artifacts,
    safe_owner_prefix,
)
from app.utils.oss_uploader import AliyunOSSUploader


_RESOURCE_METADATA = {
    "asset_id",
    "image_id",
    "type",
    "source",
    "source_document_id",
    "filename",
    "content_type",
    "size",
    "page",
    "order",
    "caption_seed",
    "near_text",
    "before_text",
    "after_text",
}


def parser_artifacts(items: list[Any], *, user_id: str) -> list[dict[str, Any]]:
    """Authorize parser inputs before any parser implementation sees them."""
    return require_owned_artifacts(items, user_id=user_id)


def _owned_resource(
    raw: dict[str, Any],
    *,
    user_id: str,
    uploader: AliyunOSSUploader,
) -> dict[str, Any] | None:
    object_path = str(raw.get("object_path") or "").strip().lstrip("/")
    filename = str(raw.get("filename") or Path(object_path).name or "resource.bin").strip()
    content_type = str(
        raw.get("content_type")
        or raw.get("mime_type")
        or mimetypes.guess_type(filename)[0]
        or "application/octet-stream"
    ).strip()

    if object_path and not object_path.startswith(safe_owner_prefix(user_id)):
        # The parser is trusted to derive this reference from an already
        # authorized source document. Re-home it before exposing it to another
        # tool so downstream authorization never needs a service-owner bypass.
        content = uploader.read_bytes(object_path)
        _url, object_path = uploader.upload_bytes_with_path(
            content=content,
            user_id=user_id,
            file_name=filename,
            content_type=content_type,
        )
    if not object_path:
        return None

    projected = {
        key: deepcopy(value)
        for key, value in raw.items()
        if key in _RESOURCE_METADATA and value not in (None, "")
    }
    projected.update(
        {
            "object_path": object_path,
            "filename": filename,
            "content_type": content_type,
        }
    )
    return projected


def public_resource_result(
    result: dict[str, Any],
    *,
    user_id: str,
    uploader: AliyunOSSUploader | None = None,
) -> dict[str, Any]:
    """Project parser output into portable ArtifactRefs and public URLs.

    Storage URLs and server-local paths are deliberately excluded from image
    and attachment references. An immutable, user-owned ``object_path`` is the
    only transport accepted by downstream ASKAI tools.
    """
    storage = uploader or AliyunOSSUploader()
    images = [
        item
        for raw in list(result.get("images") or [])
        if isinstance(raw, dict)
        for item in [_owned_resource(raw, user_id=user_id, uploader=storage)]
        if item is not None
    ]
    attachments = [
        item
        for raw in list(result.get("attachments") or [])
        if isinstance(raw, dict)
        for item in [_owned_resource(raw, user_id=user_id, uploader=storage)]
        if item is not None
    ]
    urls = [deepcopy(item) for item in list(result.get("urls") or []) if isinstance(item, dict)]
    raw_bundle = result.get("resource_bundle") if isinstance(result.get("resource_bundle"), dict) else {}
    requested = [str(item) for item in list(raw_bundle.get("requested_types") or []) if str(item)]
    bundle = {
        "requested_types": requested,
        "images": images,
        "urls": urls,
        "attachments": attachments,
        "resource_counts": {
            "images": len(images),
            "urls": len(urls),
            "attachments": len(attachments),
        },
        "source": str(raw_bundle.get("source") or "runtime_graph_parse"),
    }
    return {
        "resource_bundle": bundle,
        "resources": deepcopy(bundle),
        "images": images,
        "urls": urls,
        "attachments": attachments,
        "resource_counts": deepcopy(bundle["resource_counts"]),
    }


def own_parsed_document_images(
    result: dict[str, Any],
    *,
    user_id: str,
    uploader: AliyunOSSUploader | None = None,
) -> dict[str, Any]:
    """Re-home embedded parser images before exposing document parse output."""
    projected = deepcopy(result)
    storage = uploader or AliyunOSSUploader()
    for document in list(projected.get("parsed_documents") or []):
        if not isinstance(document, dict):
            continue
        document["embedded_images"] = [
            item
            for raw in list(document.get("embedded_images") or [])
            if isinstance(raw, dict)
            for item in [_owned_resource(raw, user_id=user_id, uploader=storage)]
            if item is not None
        ]
    return projected


__all__ = ["own_parsed_document_images", "parser_artifacts", "public_resource_result"]
