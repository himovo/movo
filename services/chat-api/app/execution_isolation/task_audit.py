"""Durable archive and cleanup for a task's complete script workspace."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import shutil
import zipfile
import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.core.db import get_db
from app.utils.oss_uploader import AliyunOSSUploader
from .script_backend import container_backend_enabled, task_key, task_workspace


MAX_AUDIT_BYTES = 512 * 1024 * 1024
MAX_INDEXED_FILES = 1000
logger = logging.getLogger(__name__)


def _archive(workspace: Path) -> tuple[bytes, list[dict], list[dict]]:
    files: list[dict] = []
    calls: list[dict] = []
    total = 0
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
        for path in sorted(workspace.rglob("*")):
            if path.is_symlink():
                continue
            if not path.is_file():
                continue
            relative = path.relative_to(workspace).as_posix()
            size = path.stat().st_size
            total += size
            if total > MAX_AUDIT_BYTES:
                raise ValueError("Audit workspace exceeds the archive limit")
            content = path.read_bytes()
            archive.writestr(relative, content)
            files.append({"path": relative, "size": size, "sha256": hashlib.sha256(content).hexdigest()})
            if path.name == "audit.json" and path.parent.parent.name == "audit":
                calls.append({"call_id": path.parent.name, **json.loads(content)})
        archive.writestr("manifest.json", json.dumps({"files": files, "calls": calls}, ensure_ascii=False))
    return memory.getvalue(), files, calls


def _manager_action(task_id: str, *, freeze: bool) -> None:
    url = os.environ["MOVO_SANDBOX_MANAGER_URL"].rstrip("/")
    token = os.environ.get("MOVO_SANDBOX_MANAGER_TOKEN", "")
    if len(token) < 32:
        raise RuntimeError("Sandbox manager token is missing")
    with httpx.Client(timeout=30, trust_env=False) as client:
        endpoint = f"{url}/v1/script-tasks/{task_key(task_id)}"
        response = (
            client.post(f"{endpoint}/freeze", headers={"Authorization": f"Bearer {token}"})
            if freeze else client.delete(endpoint, headers={"Authorization": f"Bearer {token}"})
        )
        response.raise_for_status()


async def finalize_task_audit(*, message_id: str, tenant_id: str, user_id: str,
                              conversation_id: str, status: str) -> bool:
    if not container_backend_enabled():
        return False
    workspace = task_workspace(message_id)
    if not (workspace / "work").is_dir():
        return False
    await asyncio.to_thread(_manager_action, message_id, freeze=True)
    collection = get_db().sandbox_task_audits
    audit_id = f"{tenant_id}:{message_id}"
    existing = await collection.find_one({"_id": audit_id}, {"object_path": 1, "cleanup_pending": 1})
    if not existing or not existing.get("object_path"):
        archive, files, calls = await asyncio.to_thread(_archive, workspace)
        digest = hashlib.sha256(archive).hexdigest()
        storage = AliyunOSSUploader()
        _, object_path = await asyncio.to_thread(
            storage.upload_bytes_with_path, archive, user_id, f"task-{task_key(message_id)}-audit.zip",
            "application/zip",
        )
        await collection.update_one(
            {"_id": audit_id},
            {"$set": {
                "tenant_id": tenant_id, "user_id": user_id,
                "conversation_id": conversation_id, "message_id": message_id,
                "status": status, "object_path": object_path, "sha256": digest,
                "file_count": len(files), "files": files[:MAX_INDEXED_FILES],
                "files_truncated": len(files) > MAX_INDEXED_FILES, "calls": calls,
                "completed_at": datetime.now(timezone.utc), "cleanup_pending": True,
            }}, upsert=True,
        )
    elif not existing.get("cleanup_pending"):
        await collection.update_one({"_id": audit_id}, {"$set": {"cleanup_pending": True}})
    return True


async def cleanup_task_audit(*, message_id: str, audit_id: str) -> bool:
    """Release archived resources without holding the conversation's run lock."""
    try:
        await asyncio.to_thread(_manager_action, message_id, freeze=False)
        workspace = task_workspace(message_id)
        if workspace.exists():
            await asyncio.to_thread(shutil.rmtree, workspace)
        await get_db().sandbox_task_audits.update_one(
            {"_id": audit_id}, {"$set": {"cleanup_pending": False}}
        )
        return True
    except Exception:
        logger.exception("sandbox task cleanup pending", extra={"message_id": message_id})
        return False
