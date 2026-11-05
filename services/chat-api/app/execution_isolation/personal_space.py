"""Opaque storage keys for server-side personal execution files."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from .personal_files import require_personal_parent
from .script_backend import container_backend_enabled, task_workspace


def personal_space_key(tenant_id: str, user_id: str) -> str:
    if not tenant_id or not user_id:
        raise ValueError("Personal space requires tenant and user identities")
    return hashlib.sha256(f"{tenant_id}\0{user_id}".encode()).hexdigest()


def conversation_space_key(conversation_id: str) -> str:
    if not conversation_id:
        raise ValueError("Personal space requires a conversation identity")
    return hashlib.sha256(conversation_id.encode()).hexdigest()


def ensure_personal_capacity(personal_root: Path, additional_bytes: int) -> None:
    limit = int(os.environ.get("MOVO_PERSONAL_SPACE_MAX_BYTES", str(2 * 1024 * 1024 * 1024)))
    used = sum(path.stat().st_size for path in personal_root.rglob("*")
               if not path.is_symlink() and path.is_file()) if personal_root.is_dir() else 0
    if additional_bytes < 0 or used + additional_bytes > limit:
        raise ValueError("Personal file space exceeds its storage limit")


def bind_script_task(message_id: str, tenant_id: str, user_id: str,
                     conversation_id: str) -> str:
    """Bind a trusted task identity to one personal volume before execution."""
    conversation_key = conversation_space_key(conversation_id)
    if not container_backend_enabled():
        return conversation_key
    key = personal_space_key(tenant_id, user_id)
    task_root = task_workspace(message_id)
    task_root.mkdir(parents=True, exist_ok=True)
    marker = task_root / "personal-space-key"
    if marker.exists() and marker.read_text(encoding="ascii") != key:
        raise ValueError("Script task is bound to another personal space")
    marker.write_text(key, encoding="ascii")
    root = Path(os.environ.get("MOVO_SANDBOX_WORKSPACE_ROOT", "/workspaces"))
    personal_root = root / "personal" / key
    conversation = personal_root / "conversations" / conversation_key
    require_personal_parent(personal_root, conversation.parent)
    conversation.mkdir(parents=True, exist_ok=True)
    require_personal_parent(personal_root, conversation)
    conversation.chmod(0o777)
    work = personal_root / "work"
    work.mkdir(exist_ok=True)
    require_personal_parent(personal_root, work)
    work.chmod(0o777)
    temporary = work / "tmp"
    temporary.mkdir(exist_ok=True)
    require_personal_parent(personal_root, temporary)
    temporary.chmod(0o777)
    return conversation_key
