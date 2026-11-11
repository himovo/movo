"""Session-scoped chat file preview authorization and conversion state."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import uuid
from pathlib import Path
from typing import Any

import httpx
from bson import ObjectId
from fastapi import HTTPException

from app.core.config import get_settings
from app.core.db import get_db
from app.dsh_runtime.conversation.participants_repository import SessionParticipantsRepository
from app.dsh_runtime.turn_cancellation import member_conversation
from app.utils.object_storage import ObjectStorageClient

OFFICE_SUFFIXES = {".doc", ".docx", ".xls", ".xlsx", ".xlsm", ".ppt", ".pptx"}
TEXT_SUFFIXES = {".txt", ".md", ".csv", ".tsv"}
HTML_SUFFIXES = {".html", ".htm"}
MAX_PREVIEW_SOURCE_BYTES = 200 * 1024 * 1024


async def require_session_file(session_id: str, object_path: str, tenant_id: str, user_id: str) -> dict[str, Any]:
    db = get_db()
    try:
        await member_conversation(
            db, SessionParticipantsRepository(db), session_id,
            tenant_id=tenant_id, user_id=user_id,
        )
    except (LookupError, PermissionError) as exc:
        raise HTTPException(status_code=404, detail="Chat file not found") from exc

    rows = await db.chat_messages.find({"main_id": tenant_id, "session_id": ObjectId(session_id)}).to_list(length=None)
    for row in rows:
        for document in row.get("documents") or []:
            if isinstance(document, dict) and document.get("object_path") == object_path:
                return document
        for event in row.get("execution_events") or []:
            document = _artifact_from_event(event, object_path)
            if document:
                return document
    for collection in ("execution_runs_v3", "execution_logs"):
        cursor = db[collection].find({"main_id": tenant_id, "session_id": session_id})
        async for run in cursor:
            for event in run.get("events") or []:
                document = _artifact_from_event(event, object_path)
                if document:
                    return document
    raise HTTPException(status_code=404, detail="Chat file not found")


def _artifact_from_event(event: Any, object_path: str) -> dict[str, Any] | None:
    if not isinstance(event, dict):
        return None
    if event.get("type") != "item.completed":
        return None
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None
    if event.get("item_kind") == "artifact" and payload.get("object_path") == object_path:
        return payload
    if event.get("item_kind") == "tool":
        for artifact in payload.get("artifacts") or []:
            if isinstance(artifact, dict) and artifact.get("object_path") == object_path:
                return artifact
    return None


def preview_kind(filename: str, object_path: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in OFFICE_SUFFIXES | TEXT_SUFFIXES | HTML_SUFFIXES | {".pdf"}:
        suffix = Path(object_path).suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in OFFICE_SUFFIXES:
        return "office"
    if suffix in TEXT_SUFFIXES:
        return "text"
    if suffix in HTML_SUFFIXES:
        return "html"
    return "unsupported"


def preview_id(tenant_id: str, object_path: str) -> str:
    value = f"{tenant_id}\0{object_path}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


async def get_or_start_preview(*, tenant_id: str, session_id: str, object_path: str, filename: str, retry: bool = False) -> dict[str, Any]:
    kind = preview_kind(filename, object_path)
    if kind != "office":
        return {"kind": kind, "status": "ready" if kind != "unsupported" else "unsupported"}
    db = get_db()
    identifier = preview_id(tenant_id, object_path)
    existing = await db.chat_file_previews.find_one({"_id": identifier})
    if existing and (existing.get("status") in {"queued", "ready"} or not retry):
        return {"kind": kind, "status": existing.get("status", "failed"), "error": existing.get("error", "")}

    settings = get_settings()
    if not settings.DOCUMENT_PROCESSING_SERVICE_TOKEN or not settings.MOVO_DOC_PROCESSING_CALLBACK_TOKEN:
        return {"kind": kind, "status": "failed", "error": "Preview conversion is not configured"}

    storage = ObjectStorageClient()
    if storage.storage_backend == "local" and storage.local_file_path(object_path).stat().st_size > MAX_PREVIEW_SOURCE_BYTES:
        return {"kind": kind, "status": "failed", "error": "File exceeds the preview size limit"}
    source = await asyncio.to_thread(storage.read_bytes, object_path)
    if len(source) > MAX_PREVIEW_SOURCE_BYTES:
        return {"kind": kind, "status": "failed", "error": "File exceeds the preview size limit"}
    root = Path(settings.KNOWLEDGE_LOCAL_STORAGE_DIR).expanduser().resolve()
    suffix = Path(filename).suffix.lower()
    if suffix not in OFFICE_SUFFIXES:
        suffix = Path(object_path).suffix.lower()
    attempt = uuid.uuid4().hex
    source_key = f"chat-previews/{identifier}/{attempt}/source{suffix}"
    target_key = f"chat-previews/{identifier}/{attempt}/preview.pdf"
    source_file = root / source_key
    source_file.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(source_file.write_bytes, source)
    callback_url = f"{settings.BACKEND_INTERNAL_BASE_URL.rstrip('/')}/api/chat/file-previews/{identifier}/callback"
    callback_url = f"{callback_url}?attempt={attempt}"
    payload = {
        "documentId": identifier, "mainId": tenant_id,
        "source": {"storageType": "local", "storageKey": source_key, "filename": f"source{suffix}"},
        "target": {"storageType": "local", "storageKey": target_key, "filename": "preview.pdf", "mimeType": "application/pdf"},
        "callback": {"url": callback_url, "token": settings.MOVO_DOC_PROCESSING_CALLBACK_TOKEN},
    }
    await db.chat_file_previews.update_one(
        {"_id": identifier},
        {"$set": {"tenant_id": tenant_id, "session_id": session_id, "object_path": object_path,
                  "status": "queued", "source_key": source_key, "preview_key": target_key, "error": "", "job_id": "", "attempt": attempt}},
        upsert=True,
    )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{settings.DOCUMENT_PROCESSING_BASE_URL.rstrip('/')}/api/jobs/preview-convert",
                json=payload, headers={"Authorization": f"Bearer {settings.DOCUMENT_PROCESSING_SERVICE_TOKEN}"},
            )
            response.raise_for_status()
            job_id = str(response.json().get("jobId") or "")
            if not job_id:
                raise ValueError("Conversion job ID missing")
        await db.chat_file_previews.update_one(
            {"_id": identifier, "attempt": attempt, "job_id": ""}, {"$set": {"job_id": job_id}},
        )
    except (httpx.HTTPError, ValueError) as exc:
        await db.chat_file_previews.update_one({"_id": identifier}, {"$set": {"status": "failed", "error": str(exc)[:500]}})
        await asyncio.to_thread(source_file.unlink, missing_ok=True)
        return {"kind": kind, "status": "failed", "error": "Preview conversion could not start"}
    return {"kind": kind, "status": "queued"}


async def accept_callback(identifier: str, attempt: str, token: str, payload: dict[str, Any]) -> None:
    expected = get_settings().MOVO_DOC_PROCESSING_CALLBACK_TOKEN
    if not expected or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=403, detail="Invalid callback token")
    db = get_db()
    record = await db.chat_file_previews.find_one({"_id": identifier})
    if not record or record.get("attempt") != attempt or (record.get("job_id") and record.get("job_id") != payload.get("jobId")):
        raise HTTPException(status_code=404, detail="Preview job not found")
    succeeded = payload.get("status") == "succeeded" and payload.get("previewKey") == record.get("preview_key")
    await db.chat_file_previews.update_one(
        {"_id": identifier, "attempt": attempt},
        {"$set": {"job_id": payload.get("jobId"), "status": "ready" if succeeded else "failed", "error": "" if succeeded else str(payload.get("error") or "Conversion failed")[:500]}},
    )
    source_file = Path(get_settings().KNOWLEDGE_LOCAL_STORAGE_DIR).expanduser().resolve() / str(record["source_key"])
    await asyncio.to_thread(source_file.unlink, missing_ok=True)
