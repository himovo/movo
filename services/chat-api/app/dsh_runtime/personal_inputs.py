"""Stage authorized attachments for server-side DSH plugin tools."""

from __future__ import annotations

import asyncio
import io
import os
from pathlib import Path
from typing import Any

from app.enterprise_capabilities.artifacts.references import require_owned_artifacts
from app.execution_isolation.personal_space import (
    conversation_space_key, ensure_personal_capacity, personal_space_key,
)
from app.execution_isolation.personal_files import atomic_personal_copy, require_personal_parent
from app.execution_isolation.script_backend import container_backend_enabled, task_key
from app.utils.oss_uploader import AliyunOSSUploader


MAX_INPUT_BYTES = 50 * 1024 * 1024
MAX_TURN_INPUT_BYTES = 256 * 1024 * 1024


def _safe_name(value: str, index: int) -> str:
    name = Path(str(value).replace("\\", "/")).name
    cleaned = "".join(char if char.isalnum() or char in "._-" else "_" for char in name)
    return f"{index}-{cleaned[:160] or 'attachment'}"


def _stage(binding: dict[str, Any], message_id: str,
           attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(attachments) > 20:
        raise ValueError("Too many attachments for a personal workspace turn")
    owner = str(binding["user_id"])
    admitted = require_owned_artifacts(attachments, user_id=owner)
    conversation_key = conversation_space_key(str(binding["conversation_id"]))
    personal_key = personal_space_key(str(binding["tenant_id"]), owner)
    root = Path(os.environ.get("MOVO_SANDBOX_WORKSPACE_ROOT", "/workspaces"))
    relative = Path("conversations") / conversation_key / "inputs" / task_key(message_id)
    personal_root = root / "personal" / personal_key
    destination = personal_root / relative
    require_personal_parent(personal_root, destination.parent)
    destination.mkdir(parents=True, exist_ok=True)
    require_personal_parent(personal_root, destination)
    destination.chmod(0o777)
    storage = AliyunOSSUploader()
    staged: list[dict[str, Any]] = []
    total = 0
    for index, item in enumerate(admitted):
        size = int(item.get("size") or 0)
        if size > MAX_INPUT_BYTES:
            raise ValueError("Attachment exceeds the personal space input limit")
        content = storage.read_bytes(item["object_path"])
        total += len(content)
        if len(content) > MAX_INPUT_BYTES or total > MAX_TURN_INPUT_BYTES:
            raise ValueError("Attachments exceed the personal space input limit")
        name = _safe_name(str(item.get("filename") or ""), index)
        target = destination / name
        previous_size = target.stat().st_size if target.is_file() and not target.is_symlink() else 0
        ensure_personal_capacity(personal_root, max(0, len(content) - previous_size))
        atomic_personal_copy(personal_root, target, io.BytesIO(content))
        staged.append({
            **item,
            "local_path": str(Path("/job/home") / relative / name),
        })
    return staged


async def stage_personal_inputs(binding: dict[str, Any], message_id: str,
                                attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if binding.get("execution_location") != "server" or not container_backend_enabled():
        return attachments
    return await asyncio.to_thread(_stage, binding, message_id, attachments)
