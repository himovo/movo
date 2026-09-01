from __future__ import annotations

from pathlib import Path
from typing import Any

from app.enterprise_capabilities.runtime.contracts import CapabilityExecutionContext
from app.utils.oss_uploader import AliyunOSSUploader

from .references import require_owned_artifact


def read_owned_artifact(
    artifact_value: dict[str, Any],
    *,
    context: CapabilityExecutionContext,
) -> tuple[dict[str, Any], bytes, str]:
    artifact = require_owned_artifact(dict(artifact_value or {}), user_id=context.user_id)
    object_path = str(artifact.get("object_path") or "").strip()
    if not object_path:
        raise ValueError("artifact.object_path is required")
    filename = str(artifact.get("filename") or Path(object_path).name).strip()
    return artifact, AliyunOSSUploader().read_bytes(object_path), filename


def upload_derived_artifact(
    content: bytes,
    *,
    context: CapabilityExecutionContext,
    filename: str,
    content_type: str,
) -> dict[str, Any]:
    uploader = AliyunOSSUploader()
    _, object_path = uploader.upload_bytes_with_path(
        content,
        context.user_id,
        filename,
        content_type=content_type,
    )
    return {
        "object_path": object_path,
        "filename": filename,
        "content_type": content_type,
        "size": len(content),
    }


__all__ = ["read_owned_artifact", "upload_derived_artifact"]
