"""Validation and persistence of files produced by governed scripts."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from app.utils.oss_uploader import AliyunOSSUploader


DOCUMENT_OUTPUT_EXTS = {".docx", ".pdf", ".xlsx", ".pptx", ".txt", ".md", ".json", ".csv"}
IMAGE_OUTPUT_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
ALLOWED_OUTPUT_EXTS = DOCUMENT_OUTPUT_EXTS | IMAGE_OUTPUT_EXTS


def _safe_filename(value: str, *, fallback: str) -> str:
    token = Path(str(value or "").replace("\\", "/")).name.strip()
    token = "".join(ch if ch.isalnum() or ch in "._- ()[]{}" else "_" for ch in token)
    return token[:180] or fallback


def export_script_artifacts(
    *,
    raw_artifacts: list[Any],
    output_dir: Path,
    user_id: str,
    uploader: AliyunOSSUploader | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Upload declared sandbox outputs and separate documents from images."""
    storage = uploader or AliyunOSSUploader()
    root = output_dir.resolve()
    documents: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for idx, item in enumerate(raw_artifacts):
        if not isinstance(item, dict):
            continue
        raw_path = str(item.get("path") or item.get("local_path") or "").strip()
        if not raw_path:
            continue
        path = Path(raw_path)
        if not path.is_absolute():
            path = output_dir / path
        path = path.resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError("script plugin output path must stay under output_dir") from exc
        if path in seen:
            continue
        seen.add(path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"script plugin output not found: {path.name}")
        ext = path.suffix.lower()
        if ext not in ALLOWED_OUTPUT_EXTS:
            raise ValueError(f"unsupported script plugin output extension: {ext}")
        filename = _safe_filename(
            str(item.get("name") or item.get("filename") or path.name),
            fallback=f"plugin_output_{idx}{ext}",
        )
        content_type = str(
            item.get("content_type")
            or mimetypes.guess_type(filename)[0]
            or "application/octet-stream"
        )
        signed_url, object_path = storage.upload_bytes_with_path(
            content=path.read_bytes(),
            user_id=user_id or "anonymous",
            file_name=filename,
            content_type=content_type,
        )
        artifact = {
            "type": str(item.get("type") or ext.lstrip(".") or "file").lower(),
            "url": storage.sign_url(object_path) or signed_url,
            "filename": filename,
            "title": str(item.get("title") or filename),
            "object_path": object_path,
            "content_type": content_type,
        }
        (images if ext in IMAGE_OUTPUT_EXTS else documents).append(artifact)
    return {"documents": documents, "images": images}


__all__ = ["ALLOWED_OUTPUT_EXTS", "export_script_artifacts"]
