"""Publish files written by server DSH plugins into the conversation."""

from __future__ import annotations

import asyncio
import mimetypes
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.execution_isolation.personal_space import conversation_space_key, personal_space_key
from app.utils.oss_uploader import AliyunOSSUploader


MAX_DELIVERED_FILES = 50
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024


def _started_at(binding: dict[str, Any]) -> float | None:
    started = (binding.get("active_turn") or {}).get("started_at")
    if not isinstance(started, datetime):
        return None
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return started.timestamp() - 2


def _candidates(binding: dict[str, Any]) -> list[Path]:
    if binding.get("execution_location") != "server":
        return []
    since = _started_at(binding)
    if since is None:
        return []
    root = Path(os.environ.get("MOVO_SANDBOX_WORKSPACE_ROOT", "/workspaces"))
    personal_root = (root / "personal" /
                     personal_space_key(str(binding["tenant_id"]), str(binding["user_id"])))
    conversation = personal_root / "conversations" / conversation_space_key(str(binding["conversation_id"]))
    if not conversation.is_dir() or not conversation.resolve().is_relative_to(personal_root.resolve()):
        return []
    files: list[Path] = []
    total = 0
    for path in sorted(conversation.rglob("*")):
        relative = path.relative_to(conversation)
        if relative.parts[0] in {"inputs", "outputs"} or any(part.startswith(".") for part in relative.parts):
            continue
        if path.is_symlink() or not path.is_file():
            continue
        if not path.resolve().is_relative_to(conversation.resolve()):
            continue
        metadata = path.stat()
        if metadata.st_mtime < since:
            continue
        if metadata.st_size > MAX_FILE_BYTES:
            continue
        if total + metadata.st_size > MAX_TOTAL_BYTES or len(files) >= MAX_DELIVERED_FILES:
            break
        total += metadata.st_size
        files.append(path)
    return files


def _publish(binding: dict[str, Any]) -> list[dict[str, Any]]:
    storage = AliyunOSSUploader()
    documents: list[dict[str, Any]] = []
    for path in _candidates(binding):
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        signed_url, object_path = storage.upload_bytes_with_path(
            content=path.read_bytes(),
            user_id=str(binding["user_id"]),
            file_name=path.name,
            content_type=content_type,
        )
        documents.append({
            "type": path.suffix.lower().removeprefix("."),
            "filename": path.name,
            "title": path.name,
            "content_type": content_type,
            "size": path.stat().st_size,
            "url": storage.sign_url(object_path) or signed_url,
            "object_path": object_path,
        })
    return documents


async def deliver_personal_outputs(binding: dict[str, Any]) -> list[dict[str, Any]]:
    if binding.get("execution_location") != "server":
        return []
    return await asyncio.to_thread(_publish, binding)
