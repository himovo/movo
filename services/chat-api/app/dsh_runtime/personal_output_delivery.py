"""Publish selected server Session files into the conversation."""

from __future__ import annotations

import asyncio
import mimetypes
import os
from pathlib import Path
from typing import Any

from app.execution_isolation.personal_space import conversation_space_key, personal_space_key
from app.core.db import get_db
from app.dsh_runtime.presented_output_selection import selected_paths
from app.dsh_runtime.turn_output_directory import turn_output_files
from app.utils.oss_uploader import AliyunOSSUploader


MAX_DELIVERED_FILES = 50
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024


def _conversation_root(binding: dict[str, Any]) -> Path | None:
    if binding.get("execution_location") != "server":
        return None
    root = Path(os.environ.get("MOVO_SANDBOX_WORKSPACE_ROOT", "/workspaces"))
    personal_root = (root / "personal" /
                     personal_space_key(str(binding["tenant_id"]), str(binding["user_id"])))
    conversation = personal_root / "conversations" / conversation_space_key(str(binding["conversation_id"]))
    if not conversation.is_dir() or not conversation.resolve().is_relative_to(personal_root.resolve()):
        return None
    return conversation


def _publish(binding: dict[str, Any], files: list[Path]) -> list[dict[str, Any]]:
    storage = AliyunOSSUploader()
    documents: list[dict[str, Any]] = []
    total = 0
    for path in files[:MAX_DELIVERED_FILES]:
        size = path.stat().st_size
        if size > MAX_FILE_BYTES or total + size > MAX_TOTAL_BYTES:
            continue
        total += size
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
            "size": size,
            "url": storage.sign_url(object_path) or signed_url,
            "object_path": object_path,
        })
    if files and not documents:
        raise ValueError("presented files exceed delivery limits")
    return documents


async def deliver_personal_outputs(
    binding: dict[str, Any], message_id: str, *, include_turn_directory: bool = False,
) -> list[dict[str, Any]]:
    conversation = _conversation_root(binding)
    if conversation is None:
        return []
    cursor = get_db().kernel_event_inbox.find({
        "tenant_id": str(binding["tenant_id"]),
        "user_id": str(binding["user_id"]),
        "message_id": message_id,
        "kernel_event.source.native_event_type": "deliverables/presented",
    }, {"kernel_event": 1}).sort("cursor", 1)
    events = [row["kernel_event"] async for row in cursor]
    def publish_outputs() -> list[dict[str, Any]]:
        files = selected_paths(events, conversation, str(binding["conversation_id"]))
        if include_turn_directory:
            files = list(dict.fromkeys([*files, *turn_output_files(conversation, message_id)]))
        if events and not files:
            raise FileNotFoundError("presented files were not found in the conversation workspace")
        return _publish(binding, files) if files else []

    return await asyncio.to_thread(publish_outputs)
