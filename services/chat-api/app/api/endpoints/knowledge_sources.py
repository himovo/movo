from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any, BinaryIO

from fastapi import APIRouter, Header, HTTPException, status
from starlette.responses import StreamingResponse

from app.api.endpoints.auth import _resolve_session_user
from app.core.config import get_settings
from app.core.db import get_db

router = APIRouter()

DOCUMENT_COLLECTION = "knowledge_documents"
CHUNK_COLLECTION = "knowledge_document_chunks"
OFFICE_EXTENSIONS = {"doc", "docx", "xls", "xlsx", "ppt", "pptx"}


def _needs_preview_conversion(file_ext: str) -> bool:
    return file_ext.strip().lower() in OFFICE_EXTENSIONS


def _serialize_chunk(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(chunk.get("_id") or ""),
        "documentId": str(chunk.get("document_id") or ""),
        "chunkId": str(chunk.get("chunk_id") or ""),
        "chunkStage": str(chunk.get("chunk_stage") or "rag"),
        "ordinal": int(chunk.get("ordinal") or 0),
        "text": str(chunk.get("text") or ""),
        "contextualText": str(chunk.get("contextual_text") or ""),
        "titlePath": list(chunk.get("title_path") or []),
        "pageNo": chunk.get("page_no"),
        "contentType": str(chunk.get("content_type") or "text"),
        "sourceChunkIds": list(chunk.get("source_chunk_ids") or []),
        "metadata": chunk.get("metadata") or {},
    }


async def _current_scope(authorization: str | None) -> tuple[str, str]:
    resolved = await _resolve_session_user(authorization)
    user_id = str(resolved["user"].get("_id") or "")
    main_id = str(resolved.get("main_id") or resolved["user"].get("main_id") or "default")
    return user_id, main_id


async def _find_document_or_404(document_id: str, main_id: str) -> dict[str, Any]:
    doc = await get_db()[DOCUMENT_COLLECTION].find_one(
        {"_id": document_id, "main_id": main_id, "deleted_at": None}
    )
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    return doc


def _iter_fileobj(fileobj: BinaryIO):
    try:
        while True:
            chunk = fileobj.read(1024 * 1024)
            if not chunk:
                break
            yield chunk
    finally:
        try:
            fileobj.close()
        except Exception:
            pass


def _open_local_file(storage_key: str) -> BinaryIO:
    settings = get_settings()
    root = Path(settings.KNOWLEDGE_LOCAL_STORAGE_DIR).expanduser().resolve()
    path = (root / storage_key.strip().lstrip("/").replace("\\", "/")).resolve()
    if root not in path.parents and path != root:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid file path")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")
    return path.open("rb")


def _open_oss_file(storage_key: str) -> BinaryIO:
    settings = get_settings()
    endpoint = settings.KNOWLEDGE_OSS_ENDPOINT or settings.OSS_ENDPOINT
    bucket_name = settings.KNOWLEDGE_OSS_BUCKET or settings.OSS_BUCKET_NAME
    try:
        import oss2  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="oss dependency missing") from exc
    try:
        auth = oss2.Auth(settings.OSS_ACCESS_KEY_ID, settings.OSS_ACCESS_KEY_SECRET)
        bucket = oss2.Bucket(auth, endpoint, bucket_name)
        return bucket.get_object(storage_key)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found") from exc


def _open_stored_file(doc: dict[str, Any], key: str) -> BinaryIO:
    storage_key = str(doc.get(key) or "")
    if not storage_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="preview not ready")
    storage_type = str(doc.get("storage_type") or get_settings().KNOWLEDGE_STORAGE_TYPE or "local").lower()
    if storage_type == "oss":
        return _open_oss_file(storage_key)
    return _open_local_file(storage_key)


@router.get("/knowledge/sources/documents/{document_id}")
async def get_knowledge_source_document(
    document_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _user_id, main_id = await _current_scope(authorization)
    doc = await _find_document_or_404(document_id, main_id)
    return {
        "id": str(doc.get("_id") or ""),
        "name": str(doc.get("name") or ""),
        "originalFilename": str(doc.get("original_filename") or ""),
        "fileExt": str(doc.get("file_ext") or ""),
        "mimeType": str(doc.get("mime_type") or ""),
        "previewMimeType": str(doc.get("preview_mime_type") or ""),
        "previewStatus": str(doc.get("preview_status") or ""),
        "chunkCount": int(doc.get("chunk_count") or 0),
    }


@router.get("/knowledge/sources/documents/{document_id}/chunks/{chunk_id}")
async def get_knowledge_source_chunk(
    document_id: str,
    chunk_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _user_id, main_id = await _current_scope(authorization)
    await _find_document_or_404(document_id, main_id)
    chunk = await get_db()[CHUNK_COLLECTION].find_one(
        {
            "main_id": main_id,
            "document_id": document_id,
            "chunk_id": chunk_id,
            "$or": [{"chunk_stage": "rag"}, {"chunk_stage": {"$exists": False}}],
        }
    )
    if not chunk:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chunk not found")
    return _serialize_chunk(chunk)


@router.get("/knowledge/sources/documents/{document_id}/preview")
async def get_knowledge_source_preview(
    document_id: str,
    authorization: str | None = Header(default=None),
):
    _user_id, main_id = await _current_scope(authorization)
    doc = await _find_document_or_404(document_id, main_id)
    preview_status = str(doc.get("preview_status") or "")
    if _needs_preview_conversion(str(doc.get("file_ext") or "")):
        if preview_status != "succeeded":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="preview not ready")
        storage_field = "preview_key"
    else:
        storage_field = "preview_key" if str(doc.get("preview_key") or "") else "storage_key"
    fileobj = _open_stored_file(doc, storage_field)
    storage_key = str(doc.get(storage_field) or "")
    mime = (
        str(doc.get("preview_mime_type") or "")
        if storage_field == "preview_key"
        else str(doc.get("mime_type") or "")
    ) or mimetypes.guess_type(storage_key)[0] or "application/octet-stream"
    return StreamingResponse(_iter_fileobj(fileobj), media_type=mime)
