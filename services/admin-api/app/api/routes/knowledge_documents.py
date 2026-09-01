from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import quote
import urllib.error
import urllib.request

from bson import ObjectId
from bson.dbref import DBRef
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from app.api.deps import get_current_admin_user
from app.api.time_utils import utc_iso
from app.core.config import settings
from app.core.db import get_db
from app.api.routes.knowledge_settings import get_effective_knowledge_settings, get_effective_parse_settings
from app.repositories.org_user_repository import find_account_by_username
from app.services.knowledge_storage import get_storage_service

router = APIRouter()

COLLECTION = "knowledge_documents"
CHUNK_COLLECTION = "knowledge_document_chunks"
DIRECTORY_COLLECTION = "knowledge_directories"
STATUS_VALUES = {"uploaded", "pending_parse", "parsed", "indexed", "failed"}
PROCESS_STATUS_VALUES = {"not_started", "queued", "running", "succeeded", "failed"}
SUPPORTED_KNOWLEDGE_EXTENSIONS = {"pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "txt", "md", "markdown", "png", "jpg", "jpeg", "webp"}
FILE_TYPE_GROUPS = {
    "word": ["doc", "docx"],
    "presentation": ["ppt", "pptx"],
    "spreadsheet": ["xls", "xlsx"],
    "markdown": ["md", "markdown"],
    "image": ["png", "jpg", "jpeg", "webp"],
}


class DocumentUpdatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    description: str = Field(default="", max_length=2000)
    directoryId: str | None = Field(default=None)
    knowledgeBaseId: str = Field(default="", max_length=120)
    tags: list[str] = Field(default_factory=list)
    status: str = Field(default="uploaded", pattern=r"^(uploaded|pending_parse|parsed|indexed|failed)$")


class PreviewCallbackPayload(BaseModel):
    jobId: str = Field(min_length=1)
    status: str = Field(pattern=r"^(succeeded|failed)$")
    previewKey: str = ""
    previewMimeType: str = ""
    error: str = ""


class ParseCallbackPayload(BaseModel):
    jobId: str = Field(min_length=1)
    status: str = Field(pattern=r"^(succeeded|failed)$")
    markdownKey: str = ""
    jsonKey: str = ""
    rawChunksKey: str = ""
    rawChunkCount: int = 0
    ragChunksKey: str = ""
    ragChunkCount: int = 0
    chunksKey: str = ""
    chunkCount: int = 0
    error: str = ""


class IndexCallbackPayload(BaseModel):
    jobId: str = Field(min_length=1)
    status: str = Field(pattern=r"^(succeeded|failed)$")
    indexedChunkCount: int = 0
    vectorStoreType: str = ""
    collectionName: str = ""
    error: str = ""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _time_text(value: Any) -> str:
    return utc_iso(value)


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
        "metadata": _json_safe(chunk.get("metadata") or {}),
        "status": str(chunk.get("status") or "parsed"),
        "createdAt": _time_text(chunk.get("created_at")),
        "updatedAt": _time_text(chunk.get("updated_at")),
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, DBRef):
        return {
            "collection": value.collection,
            "id": _json_safe(value.id),
            "database": value.database,
        }
    return value


def _mongo_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key).replace("$", "_"): _mongo_safe(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_mongo_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_mongo_safe(item) for item in value]
    if isinstance(value, datetime):
        return value
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, DBRef):
        return {
            "collection": value.collection,
            "id": _mongo_safe(value.id),
            "database": value.database,
        }
    if isinstance(value, int) and not isinstance(value, bool):
        if value < -(2**63) or value > 2**63 - 1:
            return str(value)
    return value


def _allowed_extensions() -> set[str]:
    return set(SUPPORTED_KNOWLEDGE_EXTENSIONS)


def _normalize_tags(raw: str | list[str] | None) -> list[str]:
    if isinstance(raw, list):
        candidates = raw
    else:
        candidates = str(raw or "").replace("，", ",").split(",")
    tags: list[str] = []
    for item in candidates:
        text = str(item or "").strip()
        if text and text not in tags:
            tags.append(text[:40])
    return tags[:20]


def _safe_filename(value: str) -> str:
    name = Path(value or "document").name.strip()
    return name or "document"


def _document_name(filename: str, fallback: str = "") -> str:
    if fallback.strip():
        return fallback.strip()[:180]
    stem = Path(filename).stem.strip()
    return (stem or filename or "未命名文档")[:180]


def _serialize(doc: dict[str, Any]) -> dict[str, Any]:
    kb_id = str(doc.get("knowledge_base_id") or "")
    return {
        "id": str(doc.get("_id") or ""),
        "mainId": str(doc.get("main_id") or "default"),
        "directoryId": kb_id,
        "knowledgeBaseId": kb_id,
        "name": str(doc.get("name") or ""),
        "description": str(doc.get("description") or ""),
        "originalFilename": str(doc.get("original_filename") or ""),
        "fileExt": str(doc.get("file_ext") or ""),
        "mimeType": str(doc.get("mime_type") or ""),
        "fileSize": int(doc.get("file_size") or 0),
        "storageType": str(doc.get("storage_type") or "local"),
        "storageBucket": str(doc.get("storage_bucket") or ""),
        "storageKey": str(doc.get("storage_key") or ""),
        "checksum": str(doc.get("checksum") or ""),
        "status": str(doc.get("status") or "uploaded"),
        "parseStatus": str(doc.get("parse_status") or "not_started"),
        "parseJobId": str(doc.get("parse_job_id") or ""),
        "parseError": str(doc.get("parse_error") or ""),
        "parseUpdatedAt": _time_text(doc.get("parse_updated_at")),
        "parsedMarkdownKey": str(doc.get("parsed_markdown_key") or ""),
        "parsedJsonKey": str(doc.get("parsed_json_key") or ""),
        "rawChunksKey": str(doc.get("raw_chunks_key") or ""),
        "rawChunkCount": int(doc.get("raw_chunk_count") or 0),
        "ragChunksKey": str(doc.get("rag_chunks_key") or ""),
        "ragChunkCount": int(doc.get("rag_chunk_count") or 0),
        "chunksKey": str(doc.get("chunks_key") or ""),
        "chunkCount": int(doc.get("chunk_count") or 0),
        "chunkStatus": str(doc.get("chunk_status") or "not_started"),
        "indexStatus": str(doc.get("index_status") or "not_started"),
        "indexJobId": str(doc.get("index_job_id") or ""),
        "indexError": str(doc.get("index_error") or ""),
        "indexedChunkCount": int(doc.get("indexed_chunk_count") or 0),
        "indexedAt": _time_text(doc.get("indexed_at")),
        "vectorStoreType": str(doc.get("vector_store_type") or ""),
        "vectorCollectionName": str(doc.get("vector_collection_name") or ""),
        "previewKey": str(doc.get("preview_key") or ""),
        "previewMimeType": str(doc.get("preview_mime_type") or ""),
        "previewStatus": str(doc.get("preview_status") or "not_required"),
        "previewJobId": str(doc.get("preview_job_id") or ""),
        "previewError": str(doc.get("preview_error") or ""),
        "previewUpdatedAt": _time_text(doc.get("preview_updated_at")),
        "tags": list(doc.get("tags") or []),
        "createdBy": str(doc.get("created_by") or ""),
        "createdByName": str(doc.get("created_by_name") or doc.get("created_by") or ""),
        "updatedBy": str(doc.get("updated_by") or ""),
        "updatedByName": str(doc.get("updated_by_name") or doc.get("updated_by") or ""),
        "createdAt": _time_text(doc.get("created_at")),
        "updatedAt": _time_text(doc.get("updated_at")),
        "deletedAt": _time_text(doc.get("deleted_at")),
        "metadata": dict(doc.get("metadata") or {}),
        "downloadUrl": f"/api/knowledge/documents/{doc.get('_id')}/content",
        "previewUrl": f"/api/knowledge/documents/{doc.get('_id')}/preview",
    }


async def _serialize_with_account_names(
    doc: dict[str, Any],
    name_cache: dict[tuple[str, str], str] | None = None,
) -> dict[str, Any]:
    item = _serialize(doc)
    main_id = str(doc.get("main_id") or "default")
    cache = name_cache if name_cache is not None else {}

    async def resolve(username: str) -> str:
        key = (main_id, username)
        if key not in cache:
            account = await find_account_by_username(username, main_id)
            cache[key] = str(account.get("display_name") or "") if account else ""
        return cache[key]

    created_by = str(doc.get("created_by") or "")
    updated_by = str(doc.get("updated_by") or "")
    created_name = str(doc.get("created_by_name") or "")
    updated_name = str(doc.get("updated_by_name") or "")
    if not created_name and created_by:
        created_name = await resolve(created_by)
    if not updated_name and updated_by:
        updated_name = await resolve(updated_by)
    item["createdByName"] = created_name
    item["updatedByName"] = updated_name
    return item


def _build_query(
    *,
    main_id: str,
    keyword: str,
    file_type: str,
    status_value: str,
    storage_type: str,
    directory_id: str | None,
    include_deleted: bool,
) -> dict[str, Any]:
    query: dict[str, Any] = {"main_id": main_id}
    if not include_deleted:
        query["deleted_at"] = None
    if directory_id and directory_id.strip():
        query["knowledge_base_id"] = directory_id.strip()
    if keyword.strip():
        pattern = {"$regex": keyword.strip(), "$options": "i"}
        query["$or"] = [
            {"name": pattern},
            {"original_filename": pattern},
        ]
    if file_type.strip():
        normalized_type = file_type.strip().lower().lstrip(".")
        extensions = FILE_TYPE_GROUPS.get(normalized_type)
        query["file_ext"] = {"$in": extensions} if extensions else normalized_type
    if status_value.strip():
        query["status"] = status_value.strip()
    if storage_type.strip():
        query["storage_type"] = storage_type.strip().lower()
    return query


def _sort_spec(sort_field: str, sort_order: str) -> list[tuple[str, int]]:
    field_map = {
        "createdAt": "created_at",
        "updatedAt": "updated_at",
        "fileSize": "file_size",
        "name": "name",
        "status": "status",
    }
    field = field_map.get(sort_field, "updated_at")
    direction = 1 if sort_order == "ascend" else -1
    return [(field, direction), ("_id", -1)]


async def _find_document_or_404(document_id: str, main_id: str, include_deleted: bool = False) -> dict[str, Any]:
    query: dict[str, Any] = {"_id": document_id, "main_id": main_id}
    if not include_deleted:
        query["deleted_at"] = None
    doc = await get_db()[COLLECTION].find_one(query)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")
    return doc


def _content_disposition(filename: str) -> str:
    safe = _safe_filename(filename).replace('"', "")
    ascii_fallback = "".join(ch if ord(ch) < 128 else "_" for ch in safe) or "document"
    encoded = quote(safe.encode("utf-8"))
    return f'inline; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded}'


def _stream_file(fileobj: Any) -> Iterator[bytes]:
    try:
        while True:
            chunk = fileobj.read(1024 * 1024)
            if not chunk:
                break
            yield chunk
    finally:
        close = getattr(fileobj, "close", None)
        if callable(close):
            close()


def _read_json_storage(storage_type: str, storage_key: str) -> dict[str, Any]:
    storage = get_storage_service(storage_type)
    with storage.open_file(storage_key) as fileobj:
        raw = fileobj.read()
    if isinstance(raw, bytes):
        text = raw.decode("utf-8")
    else:
        text = str(raw)
    parsed = json.loads(text)
    return parsed if isinstance(parsed, dict) else {}


def _user_display_name(user: dict[str, Any]) -> str:
    return str(user.get("display_name") or user.get("name") or user.get("username") or "")


def _user_login_name(user: dict[str, Any]) -> str:
    return str(user.get("username") or user.get("display_name") or user.get("name") or "")


OFFICE_EXTENSIONS = {"doc", "docx", "xls", "xlsx", "ppt", "pptx"}


def _needs_preview_conversion(file_ext: str) -> bool:
    return file_ext.strip().lower() in OFFICE_EXTENSIONS


def _request_preview_conversion(doc: dict[str, Any]) -> str:
    document_id = str(doc.get("_id") or "")
    base_url = str(settings.document_processing_base_url or "").rstrip("/")
    if not base_url:
        raise RuntimeError("document processing service url is not configured")
    source_key = str(doc.get("storage_key") or "")
    target_key = f"{source_key}.preview.pdf"
    callback_base = str(settings.admin_api_public_base_url or "").rstrip("/")
    payload = {
        "documentId": document_id,
        "mainId": str(doc.get("main_id") or "default"),
        "source": {
            "storageType": str(doc.get("storage_type") or "local"),
            "storageBucket": str(doc.get("storage_bucket") or ""),
            "storageKey": source_key,
            "filename": str(doc.get("original_filename") or doc.get("name") or "document"),
            "mimeType": str(doc.get("mime_type") or ""),
        },
        "target": {
            "storageType": str(doc.get("storage_type") or "local"),
            "storageBucket": str(doc.get("storage_bucket") or ""),
            "storageKey": target_key,
            "filename": f"{Path(str(doc.get('original_filename') or doc.get('name') or 'document')).stem}.pdf",
            "mimeType": "application/pdf",
        },
        "callback": {
            "url": f"{callback_base}/api/knowledge/documents/{document_id}/preview-callback",
            "token": settings.document_processing_callback_token,
        },
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/api/jobs/preview-convert",
        data=data,
        headers={
            "Authorization": f"Bearer {settings.document_processing_service_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            raw = response.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
    except urllib.error.URLError as exc:
        raise RuntimeError(f"document processing service unavailable: {exc}") from exc
    job_id = str(parsed.get("jobId") or "")
    if not job_id:
        raise RuntimeError("document processing service did not return jobId")
    return job_id


def _artifact_prefix(doc: dict[str, Any]) -> str:
    storage_prefix = settings.knowledge_oss_prefix.strip().strip("/") or "knowledge-documents"
    return f"{storage_prefix}/{str(doc.get('main_id') or 'default')}/{str(doc.get('_id') or '')}/artifacts"


def _request_document_parse(
    doc: dict[str, Any],
    *,
    min_chunk_size: int | None = None,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> str:
    document_id = str(doc.get("_id") or "")
    base_url = str(settings.document_processing_base_url or "").rstrip("/")
    if not base_url:
        raise RuntimeError("document processing service url is not configured")
    callback_base = str(settings.admin_api_public_base_url or "").rstrip("/")
    payload = {
        "documentId": document_id,
        "mainId": str(doc.get("main_id") or "default"),
        "source": {
            "storageType": str(doc.get("storage_type") or "local"),
            "storageBucket": str(doc.get("storage_bucket") or ""),
            "storageKey": str(doc.get("storage_key") or ""),
            "filename": str(doc.get("original_filename") or doc.get("name") or "document"),
            "mimeType": str(doc.get("mime_type") or ""),
        },
        "artifacts": {
            "storageType": str(doc.get("storage_type") or "local"),
            "storageBucket": str(doc.get("storage_bucket") or ""),
            "storagePrefix": _artifact_prefix(doc),
        },
        "callback": {
            "url": f"{callback_base}/api/knowledge/documents/{document_id}/parse-callback",
            "token": settings.document_processing_callback_token,
        },
        "minChunkSize": int(min_chunk_size or settings.knowledge_min_chunk_size or 800),
        "chunkSize": int(chunk_size or settings.knowledge_chunk_size or 1500),
        "chunkOverlap": int(chunk_overlap if chunk_overlap is not None else settings.knowledge_chunk_overlap or 80),
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/api/jobs/document-parse",
        data=data,
        headers={
            "Authorization": f"Bearer {settings.document_processing_service_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            raw = response.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
    except urllib.error.URLError as exc:
        raise RuntimeError(f"document processing service unavailable: {exc}") from exc
    job_id = str(parsed.get("jobId") or "")
    if not job_id:
        raise RuntimeError("document processing service did not return jobId")
    return job_id


async def _knowledge_settings_snapshot(main_id: str) -> dict[str, Any]:
    return await get_effective_knowledge_settings(main_id, include_secrets=True)


def _request_document_index(doc: dict[str, Any], config: dict[str, Any]) -> str:
    document_id = str(doc.get("_id") or "")
    base_url = str(settings.document_processing_base_url or "").rstrip("/")
    if not base_url:
        raise RuntimeError("document processing service url is not configured")
    callback_base = str(settings.admin_api_public_base_url or "").rstrip("/")
    payload = {
        "documentId": document_id,
        "mainId": str(doc.get("main_id") or "default"),
        "knowledgeBaseId": str(doc.get("knowledge_base_id") or ""),
        "chunkStage": "rag",
        "config": config,
        "callback": {
            "url": f"{callback_base}/api/knowledge/documents/{document_id}/index-callback",
            "token": settings.document_processing_callback_token,
        },
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/api/jobs/document-index",
        data=data,
        headers={
            "Authorization": f"Bearer {settings.document_processing_service_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            raw = response.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
    except urllib.error.URLError as exc:
        raise RuntimeError(f"document processing service unavailable: {exc}") from exc
    job_id = str(parsed.get("jobId") or "")
    if not job_id:
        raise RuntimeError("document processing service did not return jobId")
    return job_id


def _request_document_vector_delete(doc: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    document_id = str(doc.get("_id") or "")
    base_url = str(settings.document_processing_base_url or "").rstrip("/")
    if not base_url:
        raise RuntimeError("document processing service url is not configured")
    payload = {
        "documentId": document_id,
        "mainId": str(doc.get("main_id") or "default"),
        "config": config,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/api/vectors/documents/delete",
        data=data,
        headers={
            "Authorization": f"Bearer {settings.document_processing_service_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
    except urllib.error.URLError as exc:
        raise RuntimeError(f"document processing service unavailable: {exc}") from exc
    return parsed if isinstance(parsed, dict) else {}


@router.get("/stats")
async def get_document_stats(current_user: dict = Depends(get_current_admin_user)) -> dict[str, int]:
    main_id = str(current_user.get("main_id") or "default")
    db = get_db()
    base = {"main_id": main_id, "deleted_at": None}
    total = await db[COLLECTION].count_documents(base)
    indexed = await db[COLLECTION].count_documents({**base, "status": "indexed"})
    failed = await db[COLLECTION].count_documents({**base, "status": "failed"})
    local = await db[COLLECTION].count_documents({**base, "storage_type": "local"})
    oss = await db[COLLECTION].count_documents({**base, "storage_type": "oss"})
    size_result = await db[COLLECTION].aggregate([
        {"$match": base},
        {"$group": {"_id": None, "totalSize": {"$sum": {"$ifNull": ["$file_size", 0]}}}},
    ]).to_list(length=1)
    total_size = int(size_result[0].get("totalSize") or 0) if size_result else 0
    return {
        "total": total,
        "indexed": indexed,
        "failed": failed,
        "local": local,
        "oss": oss,
        "totalSize": total_size,
    }


@router.get("")
async def list_documents(
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=12, ge=1, le=100),
    keyword: str = "",
    fileType: str = "",
    statusValue: str = "",
    storageType: str = "",
    directoryId: str | None = None,
    directoryScopeId: str | None = None,
    sortField: str = "updatedAt",
    sortOrder: str = "descend",
    includeDeleted: bool = False,
    current_user: dict = Depends(get_current_admin_user),
) -> dict[str, Any]:
    main_id = str(current_user.get("main_id") or "default")
    db = get_db()
    query = _build_query(
        main_id=main_id,
        keyword=keyword,
        file_type=fileType,
        status_value=statusValue,
        storage_type=storageType,
        directory_id=directoryId,
        include_deleted=includeDeleted,
    )
    if directoryScopeId and directoryScopeId.strip():
        scope_id = directoryScopeId.strip()
        scope = await db[DIRECTORY_COLLECTION].find_one({
            "_id": scope_id,
            "main_id": main_id,
            "deleted_at": None,
        })
        if scope is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="搜索目录不存在")
        descendants = await db[DIRECTORY_COLLECTION].find({
            "main_id": main_id,
            "path_ids": scope_id,
            "deleted_at": None,
        }, {"_id": 1}).to_list(length=5000)
        scope_ids = [scope_id, *(str(item.get("_id") or "") for item in descendants)]
        query["knowledge_base_id"] = {"$in": [item for item in scope_ids if item]}
    total = await db[COLLECTION].count_documents(query)
    cursor = (
        db[COLLECTION]
        .find(query)
        .sort(_sort_spec(sortField, sortOrder))
        .skip((page - 1) * pageSize)
        .limit(pageSize)
    )
    name_cache: dict[tuple[str, str], str] = {}
    items = [await _serialize_with_account_names(doc, name_cache) async for doc in cursor]
    return {"items": items, "total": total, "page": page, "pageSize": pageSize}


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    name: str = Form(default=""),
    description: str = Form(default=""),
    directoryId: str = Form(default=""),
    knowledgeBaseId: str = Form(default=""),
    tags: str = Form(default=""),
    replaceExisting: bool = Form(default=False),
    current_user: dict = Depends(get_current_admin_user),
) -> dict[str, Any]:
    main_id = str(current_user.get("main_id") or "default")
    original_filename = _safe_filename(file.filename or "document")
    file_ext = Path(original_filename).suffix.lower().lstrip(".")
    if file_ext not in _allowed_extensions():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件类型不支持")

    actual_dir_id = (directoryId or knowledgeBaseId or "").strip()
    duplicate_query = {
        "main_id": main_id,
        "original_filename": {"$regex": f"^{re.escape(original_filename)}$", "$options": "i"},
        "deleted_at": None,
    }
    existing_documents = await get_db()[COLLECTION].find(duplicate_query).to_list(length=100)
    if existing_documents and not replaceExisting:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "DUPLICATE_FILENAME",
                "message": "知识文档中已存在同名文件",
                "filename": original_filename,
                "count": len(existing_documents),
            },
        )

    max_bytes = int(settings.knowledge_max_upload_mb or 200) * 1024 * 1024
    checksum = hashlib.sha256()
    size = 0
    suffix = f".{file_ext}" if file_ext else ""
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
            temp_path = temp.name
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="文件超过大小限制")
                checksum.update(chunk)
                temp.write(chunk)

        document_id = uuid.uuid4().hex
        storage_prefix = settings.knowledge_oss_prefix.strip().strip("/") or "knowledge-documents"
        storage_key = f"{storage_prefix}/{main_id}/{document_id}/{original_filename}"
        storage = get_storage_service()
        with open(temp_path, "rb") as source:
            stored = storage.put_file(source, storage_key)
        now = _now()
        needs_preview_conversion = _needs_preview_conversion(file_ext)
        doc = {
            "_id": document_id,
            "main_id": main_id,
            "knowledge_base_id": actual_dir_id,
            "name": _document_name(original_filename, name),
            "description": str(description or "").strip()[:2000],
            "original_filename": original_filename,
            "file_ext": file_ext,
            "mime_type": file.content_type or mimetypes.guess_type(original_filename)[0] or "application/octet-stream",
            "file_size": size,
            "storage_type": stored.storage_type,
            "storage_bucket": stored.bucket,
            "storage_key": stored.storage_key,
            "local_path": stored.local_path,
            "checksum": checksum.hexdigest(),
            "status": "uploaded",
            "parse_status": "not_started",
            "parse_job_id": "",
            "parse_error": "",
            "parse_updated_at": now,
            "parsed_markdown_key": "",
            "parsed_json_key": "",
            "raw_chunks_key": "",
            "raw_chunk_count": 0,
            "rag_chunks_key": "",
            "rag_chunk_count": 0,
            "chunks_key": "",
            "chunk_count": 0,
            "chunk_status": "not_started",
            "index_status": "not_started",
            "index_job_id": "",
            "index_error": "",
            "indexed_chunk_count": 0,
            "indexed_at": None,
            "vector_store_type": "",
            "vector_collection_name": "",
            "preview_key": "" if needs_preview_conversion else stored.storage_key,
            "preview_mime_type": "application/pdf" if needs_preview_conversion else (file.content_type or mimetypes.guess_type(original_filename)[0] or "application/octet-stream"),
            "preview_status": "pending" if needs_preview_conversion else "not_required",
            "preview_job_id": "",
            "preview_error": "",
            "preview_updated_at": now,
            "tags": _normalize_tags(tags),
            "created_by": _user_login_name(current_user),
            "created_by_name": _user_display_name(current_user),
            "updated_by": _user_login_name(current_user),
            "updated_by_name": _user_display_name(current_user),
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
            "metadata": {},
        }
        try:
            await get_db()[COLLECTION].insert_one(doc)
        except Exception:
            storage.delete_file(storage_key)
            raise
        if existing_documents:
            for existing in existing_documents:
                await _soft_delete_document(
                    existing,
                    main_id=main_id,
                    updated_by=_user_login_name(current_user),
                )
        if needs_preview_conversion:
            try:
                job_id = _request_preview_conversion(doc)
                await get_db()[COLLECTION].update_one(
                    {"_id": document_id, "main_id": main_id},
                    {
                        "$set": {
                            "preview_status": "queued",
                            "preview_job_id": job_id,
                            "preview_error": "",
                            "preview_updated_at": _now(),
                            "updated_at": _now(),
                        }
                    },
                )
                doc["preview_status"] = "queued"
                doc["preview_job_id"] = job_id
                doc["preview_updated_at"] = _now()
            except Exception as exc:
                message = str(exc)[:2000]
                await get_db()[COLLECTION].update_one(
                    {"_id": document_id, "main_id": main_id},
                    {
                        "$set": {
                            "preview_status": "failed",
                            "preview_error": message,
                            "preview_updated_at": _now(),
                            "updated_at": _now(),
                        }
                    },
                )
                doc["preview_status"] = "failed"
                doc["preview_error"] = message
                doc["preview_updated_at"] = _now()
        try:
            parse_settings = await get_effective_parse_settings(main_id)
            parse_job_id = _request_document_parse(
                doc,
                min_chunk_size=parse_settings["minChunkSize"],
                chunk_size=parse_settings["chunkSize"],
                chunk_overlap=parse_settings["chunkOverlap"],
            )
            await get_db()[COLLECTION].update_one(
                {"_id": document_id, "main_id": main_id},
                {
                    "$set": {
                        "status": "pending_parse",
                        "parse_status": "queued",
                        "chunk_status": "queued",
                        "parse_job_id": parse_job_id,
                        "parse_error": "",
                        "parse_updated_at": _now(),
                        "updated_at": _now(),
                    }
                },
            )
            doc["status"] = "pending_parse"
            doc["parse_status"] = "queued"
            doc["chunk_status"] = "queued"
            doc["parse_job_id"] = parse_job_id
            doc["parse_updated_at"] = _now()
        except Exception as exc:
            message = str(exc)[:2000]
            await get_db()[COLLECTION].update_one(
                {"_id": document_id, "main_id": main_id},
                {
                    "$set": {
                        "status": "failed",
                        "parse_status": "failed",
                        "chunk_status": "failed",
                        "parse_error": message,
                        "parse_updated_at": _now(),
                        "updated_at": _now(),
                    }
                },
            )
            doc["status"] = "failed"
            doc["parse_status"] = "failed"
            doc["chunk_status"] = "failed"
            doc["parse_error"] = message
            doc["parse_updated_at"] = _now()
        return await _serialize_with_account_names(doc)
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)
        await file.close()


@router.get("/{document_id}")
async def get_document(document_id: str, current_user: dict = Depends(get_current_admin_user)) -> dict[str, Any]:
    main_id = str(current_user.get("main_id") or "default")
    doc = await _find_document_or_404(document_id, main_id)
    return await _serialize_with_account_names(doc)


@router.post("/{document_id}/retry-parse")
async def retry_document_parse(document_id: str, current_user: dict = Depends(get_current_admin_user)) -> dict[str, Any]:
    main_id = str(current_user.get("main_id") or "default")
    db = get_db()
    doc = await _find_document_or_404(document_id, main_id)
    if str(doc.get("parse_status") or "") in {"queued", "running"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="文档正在学习中，请勿重复提交")

    now = _now()
    try:
        parse_settings = await get_effective_parse_settings(main_id)
        parse_job_id = _request_document_parse(
            doc,
            min_chunk_size=parse_settings["minChunkSize"],
            chunk_size=parse_settings["chunkSize"],
            chunk_overlap=parse_settings["chunkOverlap"],
        )
    except Exception as exc:
        message = str(exc)[:2000]
        await db[COLLECTION].update_one(
            {"_id": document_id, "main_id": main_id, "deleted_at": None},
            {
                "$set": {
                    "status": "failed",
                    "parse_status": "failed",
                    "chunk_status": "failed",
                    "parse_error": message,
                    "parse_updated_at": now,
                    "updated_at": now,
                    "updated_by": _user_login_name(current_user),
                    "updated_by_name": _user_display_name(current_user),
                }
            },
        )
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=message) from exc

    await db[COLLECTION].update_one(
        {"_id": document_id, "main_id": main_id, "deleted_at": None},
        {
            "$set": {
                "status": "pending_parse",
                "parse_status": "queued",
                "chunk_status": "queued",
                "index_status": "not_started",
                "index_job_id": "",
                "index_error": "",
                "indexed_chunk_count": 0,
                "indexed_at": None,
                "parse_job_id": parse_job_id,
                "parse_error": "",
                "parse_updated_at": now,
                "updated_at": now,
                "updated_by": _user_login_name(current_user),
                "updated_by_name": _user_display_name(current_user),
            }
        },
    )
    updated = await _find_document_or_404(document_id, main_id)
    return await _serialize_with_account_names(updated)


@router.post("/{document_id}/retry-preview")
async def retry_document_preview(document_id: str, current_user: dict = Depends(get_current_admin_user)) -> dict[str, Any]:
    main_id = str(current_user.get("main_id") or "default")
    db = get_db()
    doc = await _find_document_or_404(document_id, main_id)
    if not _needs_preview_conversion(str(doc.get("file_ext") or "")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该文档类型无需生成预览")
    if str(doc.get("preview_status") or "") in {"queued", "running"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="预览文件正在生成中，请勿重复提交")

    now = _now()
    try:
        preview_job_id = _request_preview_conversion(doc)
    except Exception as exc:
        message = str(exc)[:2000]
        await db[COLLECTION].update_one(
            {"_id": document_id, "main_id": main_id, "deleted_at": None},
            {
                "$set": {
                    "preview_status": "failed",
                    "preview_error": message,
                    "preview_updated_at": now,
                    "updated_at": now,
                    "updated_by": _user_login_name(current_user),
                    "updated_by_name": _user_display_name(current_user),
                }
            },
        )
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=message) from exc

    await db[COLLECTION].update_one(
        {"_id": document_id, "main_id": main_id, "deleted_at": None},
        {
            "$set": {
                "preview_status": "queued",
                "preview_job_id": preview_job_id,
                "preview_error": "",
                "preview_updated_at": now,
                "updated_at": now,
                "updated_by": _user_login_name(current_user),
                "updated_by_name": _user_display_name(current_user),
            }
        },
    )
    updated = await _find_document_or_404(document_id, main_id)
    return await _serialize_with_account_names(updated)


@router.get("/{document_id}/chunks")
async def list_document_chunks(
    document_id: str,
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    keyword: str = "",
    contentType: str = "",
    chunkStage: str = Query(default="rag", pattern=r"^(raw|rag|all)$"),
    current_user: dict = Depends(get_current_admin_user),
) -> dict[str, Any]:
    main_id = str(current_user.get("main_id") or "default")
    await _find_document_or_404(document_id, main_id)
    filters: list[dict[str, Any]] = [{"main_id": main_id, "document_id": document_id}]
    if chunkStage == "rag":
        filters.append({"$or": [{"chunk_stage": "rag"}, {"chunk_stage": {"$exists": False}}]})
    elif chunkStage == "raw":
        filters.append({"chunk_stage": "raw"})
    if contentType.strip():
        filters.append({"content_type": contentType.strip()})
    if keyword.strip():
        pattern = {"$regex": keyword.strip(), "$options": "i"}
        filters.append(
            {
                "$or": [
                    {"text": pattern},
                    {"contextual_text": pattern},
                    {"title_path": pattern},
                ]
            }
        )
    query: dict[str, Any] = filters[0] if len(filters) == 1 else {"$and": filters}
    db = get_db()
    total = await db[CHUNK_COLLECTION].count_documents(query)
    cursor = (
        db[CHUNK_COLLECTION]
        .find(query)
        .sort([("ordinal", 1), ("_id", 1)])
        .skip((page - 1) * pageSize)
        .limit(pageSize)
    )
    items = [_serialize_chunk(chunk) async for chunk in cursor]
    return {"items": items, "total": total, "page": page, "pageSize": pageSize}


@router.get("/{document_id}/chunks/{chunk_id}")
async def get_document_chunk(
    document_id: str,
    chunk_id: str,
    chunkStage: str = Query(default="rag", pattern=r"^(raw|rag|all)$"),
    current_user: dict = Depends(get_current_admin_user),
) -> dict[str, Any]:
    main_id = str(current_user.get("main_id") or "default")
    await _find_document_or_404(document_id, main_id)
    filters: list[dict[str, Any]] = [
        {"main_id": main_id, "document_id": document_id, "chunk_id": chunk_id}
    ]
    if chunkStage == "rag":
        filters.append({"$or": [{"chunk_stage": "rag"}, {"chunk_stage": {"$exists": False}}]})
    elif chunkStage == "raw":
        filters.append({"chunk_stage": "raw"})
    query: dict[str, Any] = filters[0] if len(filters) == 1 else {"$and": filters}
    chunk = await get_db()[CHUNK_COLLECTION].find_one(query)
    if not chunk:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chunk not found")
    return _serialize_chunk(chunk)


@router.put("/{document_id}")
async def update_document(
    document_id: str,
    payload: DocumentUpdatePayload,
    current_user: dict = Depends(get_current_admin_user),
) -> dict[str, Any]:
    main_id = str(current_user.get("main_id") or "default")
    if payload.status not in STATUS_VALUES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文档状态无效")
    actual_dir_id = (payload.directoryId or payload.knowledgeBaseId or "").strip()
    patch = {
        "name": payload.name.strip(),
        "description": payload.description.strip(),
        "knowledge_base_id": actual_dir_id,
        "tags": _normalize_tags(payload.tags),
        "status": payload.status,
        "updated_by": _user_login_name(current_user),
        "updated_by_name": _user_display_name(current_user),
        "updated_at": _now(),
    }
    result = await get_db()[COLLECTION].update_one(
        {"_id": document_id, "main_id": main_id, "deleted_at": None},
        {"$set": patch},
    )
    if not result.matched_count:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")
    doc = await _find_document_or_404(document_id, main_id)
    return await _serialize_with_account_names(doc)


async def _soft_delete_document(doc: dict[str, Any], *, main_id: str, updated_by: str) -> None:
    db = get_db()
    document_id = str(doc.get("_id") or "")
    now = _now()
    result = await db[COLLECTION].update_one(
        {"_id": document_id, "main_id": main_id, "deleted_at": None},
        {
            "$set": {
                "deleted_at": now,
                "updated_at": now,
                "updated_by": updated_by,
                "vector_delete_status": "pending",
                "vector_delete_error": "",
            }
        },
    )
    if not result.matched_count:
        return
    await db[CHUNK_COLLECTION].update_many(
        {"document_id": document_id, "main_id": main_id},
        {
            "$set": {
                "deleted_at": now,
                "status": "deleted",
                "index_status": "deleted",
                "embedding_status": "deleted",
                "updated_at": now,
            }
        },
    )
    try:
        config = await _knowledge_settings_snapshot(main_id)
        vector_result = _request_document_vector_delete(doc, config)
        await db[COLLECTION].update_one(
            {"_id": document_id, "main_id": main_id},
            {
                "$set": {
                    "vector_delete_status": "succeeded",
                    "vector_deleted_at": _now(),
                    "vector_deleted_count": int(vector_result.get("deleted") or 0),
                    "vector_delete_error": "",
                    "vector_store_type": str(vector_result.get("vectorStoreType") or doc.get("vector_store_type") or ""),
                    "vector_collection_name": str(vector_result.get("collectionName") or doc.get("vector_collection_name") or ""),
                }
            },
        )
    except Exception as exc:
        await db[COLLECTION].update_one(
            {"_id": document_id, "main_id": main_id},
            {
                "$set": {
                    "vector_delete_status": "failed",
                    "vector_delete_error": str(exc)[:2000],
                    "vector_deleted_at": _now(),
                }
            },
        )


@router.delete("/{document_id}")
async def delete_document(document_id: str, current_user: dict = Depends(get_current_admin_user)) -> dict[str, bool]:
    main_id = str(current_user.get("main_id") or "default")
    doc = await _find_document_or_404(document_id, main_id)
    await _soft_delete_document(
        doc,
        main_id=main_id,
        updated_by=_user_login_name(current_user),
    )
    return {"success": True}


@router.post("/{document_id}/restore")
async def restore_document(document_id: str, current_user: dict = Depends(get_current_admin_user)) -> dict[str, Any]:
    main_id = str(current_user.get("main_id") or "default")
    db = get_db()
    result = await db[COLLECTION].update_one(
        {"_id": document_id, "main_id": main_id, "deleted_at": {"$ne": None}},
        {"$set": {"deleted_at": None, "updated_at": _now(), "updated_by": str(current_user.get("username") or "")}},
    )
    if not result.matched_count:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在或未删除")
    await db[CHUNK_COLLECTION].update_many(
        {"document_id": document_id, "main_id": main_id},
        {
            "$set": {
                "updated_at": _now(),
            },
            "$unset": {
                "deleted_at": "",
                "status": "",
            },
        },
    )
    doc = await _find_document_or_404(document_id, main_id)
    return await _serialize_with_account_names(doc)


@router.post("/{document_id}/preview-callback")
async def preview_conversion_callback(
    document_id: str,
    payload: PreviewCallbackPayload,
    authorization: str | None = Header(default=None),
) -> dict[str, bool]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing callback token")
    token = authorization.replace("Bearer ", "", 1).strip()
    if token != settings.document_processing_callback_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid callback token")

    now = _now()
    if payload.status == "succeeded":
        patch = {
            "preview_status": "succeeded",
            "preview_key": payload.previewKey,
            "preview_mime_type": payload.previewMimeType or "application/pdf",
            "preview_error": "",
            "preview_updated_at": now,
            "updated_at": now,
        }
    else:
        patch = {
            "preview_status": "failed",
            "preview_error": payload.error[:2000],
            "preview_updated_at": now,
            "updated_at": now,
        }
    result = await get_db()[COLLECTION].update_one(
        {"_id": document_id, "preview_job_id": payload.jobId, "deleted_at": None},
        {"$set": patch},
    )
    if not result.matched_count:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档或转换任务不存在")
    return {"success": True}


@router.post("/{document_id}/parse-callback")
async def document_parse_callback(
    document_id: str,
    payload: ParseCallbackPayload,
    authorization: str | None = Header(default=None),
) -> dict[str, bool]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing callback token")
    token = authorization.replace("Bearer ", "", 1).strip()
    if token != settings.document_processing_callback_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid callback token")

    db = get_db()
    doc = await db[COLLECTION].find_one({"_id": document_id, "parse_job_id": payload.jobId, "deleted_at": None})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档或解析任务不存在")

    now = _now()
    if payload.status == "failed":
        await db[COLLECTION].update_one(
            {"_id": document_id, "parse_job_id": payload.jobId, "deleted_at": None},
            {
                "$set": {
                    "status": "failed",
                    "parse_status": "failed",
                    "chunk_status": "failed",
                    "parse_error": payload.error[:2000],
                    "parse_updated_at": now,
                    "updated_at": now,
                }
            },
        )
        return {"success": True}

    default_chunks_key = payload.chunksKey
    raw_chunks_key = payload.rawChunksKey or default_chunks_key
    rag_chunks_key = payload.ragChunksKey or default_chunks_key

    raw_chunks_payload = _read_json_storage(str(doc.get("storage_type") or "local"), raw_chunks_key) if raw_chunks_key else {}
    rag_chunks_payload = _read_json_storage(str(doc.get("storage_type") or "local"), rag_chunks_key) if rag_chunks_key else {}
    raw_chunks = raw_chunks_payload.get("chunks") if isinstance(raw_chunks_payload, dict) else []
    rag_chunks = rag_chunks_payload.get("chunks") if isinstance(rag_chunks_payload, dict) else []
    if not isinstance(raw_chunks, list):
        raw_chunks = []
    if not isinstance(rag_chunks, list):
        rag_chunks = []
    if not raw_chunks and rag_chunks_key == raw_chunks_key:
        raw_chunks = rag_chunks

    await db[CHUNK_COLLECTION].delete_many({"document_id": document_id, "main_id": str(doc.get("main_id") or "default")})
    rows: list[dict[str, Any]] = []

    def append_rows(chunks: list[Any], stage: str) -> None:
        for index, chunk in enumerate(chunks):
            if not isinstance(chunk, dict):
                continue
            text = str(chunk.get("text") or "").strip()
            if not text:
                continue
            chunk_id = str(chunk.get("chunkId") or f"{stage}_{index + 1:06d}")
            metadata = dict(chunk.get("metadata") or {})
            raw_source_chunk_ids = chunk.get("sourceChunkIds") or metadata.get("sourceChunkIds") or []
            if isinstance(raw_source_chunk_ids, str):
                source_chunk_ids = [raw_source_chunk_ids]
            elif isinstance(raw_source_chunk_ids, list):
                source_chunk_ids = raw_source_chunk_ids
            else:
                source_chunk_ids = []
            rows.append(
                {
                    "_id": f"{document_id}:{stage}:{chunk_id}",
                    "main_id": str(doc.get("main_id") or "default"),
                    "knowledge_base_id": str(doc.get("knowledge_base_id") or ""),
                    "document_id": document_id,
                    "chunk_id": chunk_id,
                    "chunk_stage": stage,
                    "ordinal": int(chunk.get("ordinal") or index),
                    "text": text,
                    "contextual_text": str(chunk.get("contextualText") or text),
                    "title_path": list(chunk.get("titlePath") or []),
                    "page_no": chunk.get("pageNo"),
                    "content_type": str(chunk.get("contentType") or "text"),
                    "source_chunk_ids": [str(item) for item in source_chunk_ids if str(item).strip()],
                    "metadata": _mongo_safe(metadata),
                    "status": "parsed",
                    "created_at": now,
                    "updated_at": now,
                }
            )

    append_rows(raw_chunks, "raw")
    append_rows(rag_chunks, "rag")
    if rows:
        await db[CHUNK_COLLECTION].insert_many(rows, ordered=False)
    rag_count = sum(1 for row in rows if row.get("chunk_stage") == "rag")
    raw_count = sum(1 for row in rows if row.get("chunk_stage") == "raw")

    await db[COLLECTION].update_one(
        {"_id": document_id, "parse_job_id": payload.jobId, "deleted_at": None},
        {
            "$set": {
                "status": "parsed",
                "parse_status": "succeeded",
                "chunk_status": "succeeded",
                "parse_error": "",
                "parse_updated_at": now,
                "parsed_markdown_key": payload.markdownKey,
                "parsed_json_key": payload.jsonKey,
                "raw_chunks_key": raw_chunks_key,
                "raw_chunk_count": raw_count,
                "rag_chunks_key": rag_chunks_key,
                "rag_chunk_count": rag_count,
                "chunks_key": rag_chunks_key or payload.chunksKey,
                "chunk_count": rag_count,
                "index_status": "not_started",
                "index_job_id": "",
                "index_error": "",
                "indexed_chunk_count": 0,
                "indexed_at": None,
                "updated_at": now,
            }
        },
    )
    config = await _knowledge_settings_snapshot(str(doc.get("main_id") or "default"))
    if bool((config.get("index") or {}).get("autoIndexAfterParse", True)) and rag_count > 0:
        index_doc = {
            **doc,
            "rag_chunk_count": rag_count,
            "chunk_count": rag_count,
        }
        try:
            index_job_id = _request_document_index(index_doc, config)
        except Exception as exc:
            await db[COLLECTION].update_one(
                {"_id": document_id, "deleted_at": None},
                {
                    "$set": {
                        "index_status": "failed",
                        "index_error": str(exc)[:2000],
                        "updated_at": _now(),
                    }
                },
            )
        else:
            await db[COLLECTION].update_one(
                {"_id": document_id, "deleted_at": None},
                {
                    "$set": {
                        "index_status": "queued",
                        "index_job_id": index_job_id,
                        "index_error": "",
                        "updated_at": _now(),
                    }
                },
            )
    return {"success": True}


@router.post("/{document_id}/index-callback")
async def document_index_callback(
    document_id: str,
    payload: IndexCallbackPayload,
    authorization: str | None = Header(default=None),
) -> dict[str, bool]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing callback token")
    token = authorization.replace("Bearer ", "", 1).strip()
    if token != settings.document_processing_callback_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid callback token")

    db = get_db()
    doc = await db[COLLECTION].find_one({"_id": document_id, "index_job_id": payload.jobId, "deleted_at": None})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档或索引任务不存在")

    now = _now()
    if payload.status == "failed":
        await db[COLLECTION].update_one(
            {"_id": document_id, "index_job_id": payload.jobId, "deleted_at": None},
            {
                "$set": {
                    "status": "parsed",
                    "index_status": "failed",
                    "index_error": payload.error[:2000],
                    "updated_at": now,
                }
            },
        )
        return {"success": True}

    await db[COLLECTION].update_one(
        {"_id": document_id, "index_job_id": payload.jobId, "deleted_at": None},
        {
            "$set": {
                "status": "indexed",
                "index_status": "succeeded",
                "index_error": "",
                "indexed_chunk_count": int(payload.indexedChunkCount or 0),
                "indexed_at": now,
                "vector_store_type": payload.vectorStoreType,
                "vector_collection_name": payload.collectionName,
                "updated_at": now,
            }
        },
    )
    return {"success": True}


@router.post("/{document_id}/retry-index")
async def retry_document_index(document_id: str, current_user: dict = Depends(get_current_admin_user)) -> dict[str, Any]:
    main_id = str(current_user.get("main_id") or "default")
    db = get_db()
    doc = await _find_document_or_404(document_id, main_id)
    if str(doc.get("index_status") or "") in {"queued", "running"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="文档正在索引中，请勿重复提交")
    if str(doc.get("chunk_status") or "") != "succeeded" or int(doc.get("rag_chunk_count") or doc.get("chunk_count") or 0) <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文档尚未完成分段，无法索引")

    config = await _knowledge_settings_snapshot(main_id)
    try:
        index_job_id = _request_document_index(doc, config)
    except Exception as exc:
        message = str(exc)[:2000]
        await db[COLLECTION].update_one(
            {"_id": document_id, "main_id": main_id, "deleted_at": None},
            {
                "$set": {
                    "index_status": "failed",
                    "index_error": message,
                    "updated_at": _now(),
                    "updated_by": _user_login_name(current_user),
                    "updated_by_name": _user_display_name(current_user),
                }
            },
        )
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=message) from exc

    await db[COLLECTION].update_one(
        {"_id": document_id, "main_id": main_id, "deleted_at": None},
        {
            "$set": {
                "index_status": "queued",
                "index_job_id": index_job_id,
                "index_error": "",
                "updated_at": _now(),
                "updated_by": _user_login_name(current_user),
                "updated_by_name": _user_display_name(current_user),
            }
        },
    )
    updated = await _find_document_or_404(document_id, main_id)
    return await _serialize_with_account_names(updated)


@router.get("/{document_id}/content")
async def get_document_content(document_id: str, current_user: dict = Depends(get_current_admin_user)) -> StreamingResponse:
    main_id = str(current_user.get("main_id") or "default")
    doc = await _find_document_or_404(document_id, main_id)
    storage = get_storage_service(str(doc.get("storage_type") or "local"))
    fileobj = storage.open_file(str(doc.get("storage_key") or ""))
    media_type = str(doc.get("mime_type") or "") or "application/octet-stream"
    return StreamingResponse(
        _stream_file(fileobj),
        media_type=media_type,
        headers={"Content-Disposition": _content_disposition(str(doc.get("original_filename") or doc.get("name") or "document"))},
    )


@router.get("/{document_id}/preview")
async def get_document_preview(document_id: str, current_user: dict = Depends(get_current_admin_user)) -> StreamingResponse:
    main_id = str(current_user.get("main_id") or "default")
    doc = await _find_document_or_404(document_id, main_id)
    storage = get_storage_service(str(doc.get("storage_type") or "local"))
    preview_status = str(doc.get("preview_status") or "not_required")
    preview_key = str(doc.get("preview_key") or "")
    if _needs_preview_conversion(str(doc.get("file_ext") or "")) and preview_status not in {"succeeded"}:
        detail = "预览文件正在生成，请稍后刷新。"
        if preview_status == "failed":
            detail = str(doc.get("preview_error") or "预览文件生成失败，可下载原文件查看。")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    storage_key = preview_key or str(doc.get("storage_key") or "")
    try:
        fileobj = storage.open_file(storage_key)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="预览文件不存在") from exc
    media_type = str(doc.get("preview_mime_type") or doc.get("mime_type") or "") or "application/octet-stream"
    filename = str(doc.get("original_filename") or doc.get("name") or "document")
    if media_type == "application/pdf" and not filename.lower().endswith(".pdf"):
        filename = f"{Path(filename).stem}.pdf"
    return StreamingResponse(
        _stream_file(fileobj),
        media_type=media_type,
        headers={"Content-Disposition": _content_disposition(filename)},
    )


async def ensure_indexes() -> None:
    db = get_db()
    await db[COLLECTION].create_index([("main_id", 1), ("deleted_at", 1), ("updated_at", -1)], name="knowledge_docs_main_updated")
    await db[COLLECTION].create_index([("main_id", 1), ("file_ext", 1), ("updated_at", -1)], name="knowledge_docs_file_ext")
    await db[COLLECTION].create_index([("main_id", 1), ("status", 1), ("updated_at", -1)], name="knowledge_docs_status")
    await db[COLLECTION].create_index([("main_id", 1), ("storage_type", 1)], name="knowledge_docs_storage_type")
    await db[COLLECTION].create_index([("main_id", 1), ("checksum", 1)], name="knowledge_docs_checksum")
    await db[COLLECTION].create_index([("preview_job_id", 1)], name="knowledge_docs_preview_job")
    await db[COLLECTION].create_index([("parse_job_id", 1)], name="knowledge_docs_parse_job")
    await db[COLLECTION].create_index([("main_id", 1), ("knowledge_base_id", 1), ("deleted_at", 1), ("updated_at", -1)], name="knowledge_docs_dir_updated")
    await db[CHUNK_COLLECTION].create_index([("main_id", 1), ("document_id", 1), ("chunk_stage", 1), ("ordinal", 1)], name="knowledge_chunks_doc_stage_order")
    await db[CHUNK_COLLECTION].create_index([("main_id", 1), ("knowledge_base_id", 1), ("chunk_stage", 1), ("document_id", 1)], name="knowledge_chunks_kb_stage_doc")
