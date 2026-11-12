"""Authorized preview endpoints for files attached to a chat session."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from app.api.endpoints.auth import _resolve_session_user
from app.core.db import get_db
from app.services.chat_file_previews import (
    HTML_SUFFIXES, TEXT_SUFFIXES, CODE_SUFFIXES, accept_callback, get_or_start_preview, preview_id,
    preview_kind, require_session_file,
)
from app.services.knowledge_preview_stream import parse_byte_range, preview_response
from app.utils.object_storage import ObjectStorageClient
from app.utils.oss_uploader import AliyunOSSUploader

router = APIRouter(tags=["chat-file-preview"])


class PreviewRequest(BaseModel):
    session_id: str = Field(min_length=1)
    object_path: str = Field(min_length=1)
    retry: bool = False


class DraftPreviewRequest(BaseModel):
    object_path: str = Field(min_length=1)
    retry: bool = False


async def _authorized_file(session_id: str, object_path: str, authorization: str | None):
    resolved = await _resolve_session_user(authorization)
    tenant_id = str(resolved.get("main_id") or "default")
    user_id = str(resolved["user"].get("_id") or "")
    document = await require_session_file(session_id, object_path, tenant_id, user_id)
    return document, tenant_id


async def _authorized_draft(object_path: str, authorization: str | None):
    resolved = await _resolve_session_user(authorization)
    tenant_id = str(resolved.get("main_id") or "default")
    user_id = str(resolved["user"].get("_id") or "")
    document = await get_db().chat_uploads.find_one({"_id": object_path, "main_id": tenant_id, "user_id": user_id})
    if not document:
        raise HTTPException(status_code=404, detail="Chat file not found")
    return document, tenant_id


@router.post("/chat/file-previews/drafts")
async def prepare_draft_preview(payload: DraftPreviewRequest, authorization: str | None = Header(default=None)) -> dict:
    document, tenant_id = await _authorized_draft(payload.object_path, authorization)
    filename = str(document.get("filename") or payload.object_path)
    result = await get_or_start_preview(
        tenant_id=tenant_id, session_id="draft", object_path=payload.object_path,
        filename=filename, retry=payload.retry,
    )
    if result["status"] == "ready":
        result["url"] = f"/askai-api/api/chat/file-previews/drafts/content?object_path={quote(payload.object_path, safe='')}"
        if result["kind"] == "html":
            result["render_url"] = AliyunOSSUploader().sign_url(payload.object_path)
    result["filename"] = filename
    return result


@router.get("/chat/file-previews/drafts/content")
async def draft_preview_content(object_path: str, request: Request, authorization: str | None = Header(default=None)):
    document, tenant_id = await _authorized_draft(object_path, authorization)
    return await _serve_content(document, tenant_id, object_path, request)


@router.post("/chat/file-previews")
async def prepare_preview(payload: PreviewRequest, authorization: str | None = Header(default=None)) -> dict:
    document, tenant_id = await _authorized_file(payload.session_id, payload.object_path, authorization)
    filename = str(document.get("filename") or document.get("title") or payload.object_path)
    result = await get_or_start_preview(
        tenant_id=tenant_id, session_id=payload.session_id,
        object_path=payload.object_path, filename=filename, retry=payload.retry,
    )
    if result["status"] == "ready":
        result["url"] = f"/askai-api/api/chat/file-previews/{payload.session_id}/content?object_path={quote(payload.object_path, safe='')}"
        if result["kind"] == "html":
            result["render_url"] = AliyunOSSUploader().sign_url(payload.object_path)
    result["filename"] = filename
    return result


@router.get("/chat/file-previews/{session_id}/content")
async def preview_content(
    session_id: str, object_path: str, request: Request,
    authorization: str | None = Header(default=None),
):
    document, tenant_id = await _authorized_file(session_id, object_path, authorization)
    return await _serve_content(document, tenant_id, object_path, request)


async def _serve_content(document: dict, tenant_id: str, object_path: str, request: Request):
    filename = str(document.get("filename") or document.get("title") or object_path)
    kind = preview_kind(filename, object_path)
    if kind == "pdf":
        storage = ObjectStorageClient()
        if storage.storage_backend == "oss":
            return _oss_pdf_content(storage, object_path, request.headers.get("range", ""))
        return _local_content(object_path, "application/pdf")
    if kind in {"text", "code"}:
        suffix = Path(filename).suffix.lower()
        return _text_content(object_path, suffix if suffix in TEXT_SUFFIXES | CODE_SUFFIXES else Path(object_path).suffix.lower())
    if kind == "html":
        return _text_content(object_path, ".html")
    if kind == "office":
        identifier = preview_id(tenant_id, object_path)
        record = await get_db().chat_file_previews.find_one({"_id": identifier, "status": "ready"})
        if not record:
            raise HTTPException(status_code=409, detail="Preview is not ready")
        return preview_response(
            document={"storage_type": "local", "preview_key": record["preview_key"]},
            storage_field="preview_key", media_type="application/pdf",
            range_header=request.headers.get("range", ""),
        )
    raise HTTPException(status_code=415, detail="Unsupported preview format")


def _local_content(object_path: str, media_type: str):
    from fastapi.responses import FileResponse

    file_path = ObjectStorageClient().local_file_path(object_path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, media_type=media_type, content_disposition_type="inline")


def _oss_pdf_content(storage: ObjectStorageClient, object_path: str, range_header: str):
    bucket = storage.bucket
    if bucket is None:
        raise HTTPException(status_code=503, detail="Object storage is unavailable")
    size = int(bucket.head_object(object_path).content_length)
    try:
        byte_range = parse_byte_range(range_header, size)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=416, detail="Invalid byte range", headers={"Content-Range": f"bytes */{size}"}) from exc
    headers = {"Accept-Ranges": "bytes", "Content-Disposition": "inline"}
    if byte_range:
        start, end = byte_range
        source = bucket.get_object(object_path, byte_range=(start, end))
        headers.update({"Content-Length": str(end - start + 1), "Content-Range": f"bytes {start}-{end}/{size}"})
    else:
        source = bucket.get_object(object_path)
        headers["Content-Length"] = str(size)

    def chunks():
        try:
            while chunk := source.read(1024 * 1024):
                yield chunk
        finally:
            source.close()

    return StreamingResponse(chunks(), status_code=206 if byte_range else 200, media_type="application/pdf", headers=headers)


def _text_content(object_path: str, suffix: str):
    if suffix not in TEXT_SUFFIXES | HTML_SUFFIXES | CODE_SUFFIXES:
        raise HTTPException(status_code=415, detail="Unsupported preview format")
    storage = ObjectStorageClient()
    if storage.storage_backend == "local":
        file_path = storage.local_file_path(object_path)
        if file_path.stat().st_size > 5 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Text preview is too large")
    content = storage.read_bytes(object_path)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Text preview is too large")
    return Response(content=content.decode("utf-8", errors="replace"), media_type="text/plain; charset=utf-8")


@router.post("/chat/file-previews/{identifier}/callback")
async def preview_callback(identifier: str, payload: dict, attempt: str, authorization: str | None = Header(default=None)) -> dict:
    token = (authorization or "").removeprefix("Bearer ").strip()
    await accept_callback(identifier, attempt, token, payload)
    return {"ok": True}
