from __future__ import annotations
from app.infrastructure.observability.config import log_print

import json
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from bson import ObjectId
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import AliasChoices, BaseModel, Field

from app.core.db import get_db
from app.api.endpoints.auth import _resolve_session_user
from app.core.tenant import add_main_scope, resolve_main_id
from app.utils.oss_uploader import AliyunOSSUploader
from app.llm.factory import get_llm_client
from app.llm.types import Message, Role
from app.context_engine.compactor import context_compactor
from app.context_engine.project_memory import project_memory_service
from app.services.session_persistence_service import session_persistence_service
from app.services.session_runtime_context import attach_session_runtime_contexts
from app.infrastructure.execution_events.history import normalize_execution_history

router = APIRouter()

COMPACTION_TRIGGER_MESSAGES = 40
COMPACTION_KEEP_RECENT = 20


async def _authorized_scope(
    authorization: str | None,
    *,
    claimed_user_id: str,
    claimed_main_id: str | None,
) -> tuple[str, str]:
    resolved = await _resolve_session_user(authorization if isinstance(authorization, str) else None)
    actual_user_id = str(resolved["user"].get("_id") or "")
    actual_main_id = resolve_main_id(resolved["main_id"])
    if claimed_user_id and claimed_user_id != actual_user_id:
        raise HTTPException(status_code=404, detail="Session not found")
    if claimed_main_id and resolve_main_id(claimed_main_id) != actual_main_id:
        raise HTTPException(status_code=404, detail="Session not found")
    return actual_user_id, actual_main_id


class MessageIn(BaseModel):
    role: str = Field(..., description="Message role: user/assistant/system")
    content: str = Field(..., description="Message content")
    plan: Optional[dict] = Field(None, description="Optional plan payload")
    progress: Optional[list] = Field(None, description="Optional progress logs")
    documents: Optional[list] = Field(None, description="Optional generated documents")
    images: Optional[list] = Field(None, description="Optional uploaded image metadata")
    evidence_bundles: Optional[list] = Field(None, validation_alias=AliasChoices("evidence_bundles", "evidenceBundles"), description="Optional persisted evidence bundles")
    message_id: Optional[str] = Field(None, description="Streaming message id from chat completion (X-Message-Id)")
    execution_events: Optional[list] = Field(None, description="Replayed V3 execution events on session GET (read-only)")
    trigger_source: Optional[str] = None
    scheduled_job_id: Optional[str] = None
    scheduled_run_id: Optional[str] = None
    created_at: Optional[datetime] = None


class SessionCreate(BaseModel):
    user_id: str = Field(..., description="User ID from login")
    main_id: Optional[str] = Field(None, validation_alias=AliasChoices("main_id", "mainId"), description="Tenant / main account ID")
    title: Optional[str] = Field(None, description="Session title")
    messages: Optional[List[MessageIn]] = Field(default_factory=list)


class SessionSummary(BaseModel):
    id: str
    user_id: str
    main_id: str = "default"
    title: str
    created_at: datetime
    updated_at: datetime
    last_message_at: Optional[datetime] = None
    last_message_preview: Optional[str] = None
    message_count: int = 0
    latest_artifact_ref: Optional[dict] = None
    active_document: Optional[dict] = None
    active_document_id: Optional[str] = None
    document_count: int = 0
    active_run: Optional[dict] = None
    scheduled_unread: bool = False
    last_scheduled_run: Optional[dict] = None
    pending_approval_count: int = 0
    execution_location: str = "server"
    runtime_preset_id: str = "askai-enterprise"
    code_project: Optional[dict] = None


class SessionDetail(SessionSummary):
    messages: List[MessageIn] = Field(default_factory=list)


class SessionSearchResult(SessionSummary):
    match_type: str = "message"
    snippets: List[str] = Field(default_factory=list)
    matched_message_count: int = 0


class MessageAppend(BaseModel):
    user_id: str = Field(..., description="User ID from login")
    main_id: Optional[str] = Field(None, validation_alias=AliasChoices("main_id", "mainId"), description="Tenant / main account ID")
    messages: List[MessageIn] = Field(..., description="Messages to append")


class SessionUpdate(BaseModel):
    user_id: str = Field(..., description="User ID from login")
    main_id: Optional[str] = Field(None, validation_alias=AliasChoices("main_id", "mainId"), description="Tenant / main account ID")
    title: str = Field(..., min_length=1, max_length=160, description="Session title")


class ApiResponse(BaseModel):
    code: int = 0
    message: str | None = None
    data: object | None = None


def _serialize_session(doc: dict) -> dict:
    return {
        "id": str(doc.get("_id")),
        "user_id": doc.get("user_id"),
        "main_id": resolve_main_id(doc.get("main_id")),
        "title": doc.get("title"),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
        "last_message_at": doc.get("last_message_at"),
        "last_message_preview": doc.get("last_message_preview"),
        "message_count": doc.get("message_count", 0),
        "latest_artifact_ref": doc.get("latest_artifact_ref"),
        "active_document": doc.get("active_document"),
        "active_document_id": doc.get("active_document_id"),
        "document_count": len(list(doc.get("document_registry") or [])),
        "active_run": doc.get("active_run"),
        "scheduled_unread": bool(doc.get("scheduled_unread")),
        "last_scheduled_run": doc.get("last_scheduled_run"),
        "pending_approval_count": int(doc.get("pending_approval_count") or 0),
        "execution_location": str(doc.get("execution_location") or "server"),
        "runtime_preset_id": str(doc.get("runtime_preset_id") or "askai-enterprise"),
        "code_project": doc.get("code_project"),
    }


def _serialize_session_summary(doc: dict) -> dict:
    # Lightweight payload for sidebar history list; avoid returning large active_document content.
    return {
        "id": str(doc.get("_id")),
        "user_id": doc.get("user_id"),
        "main_id": resolve_main_id(doc.get("main_id")),
        "title": doc.get("title"),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
        "last_message_at": doc.get("last_message_at"),
        "last_message_preview": doc.get("last_message_preview"),
        "message_count": doc.get("message_count", 0),
        "latest_artifact_ref": doc.get("latest_artifact_ref"),
        "active_document": None,
        "active_document_id": doc.get("active_document_id"),
        "document_count": int(doc.get("document_count") or 0),
        "active_run": doc.get("active_run"),
        "scheduled_unread": bool(doc.get("scheduled_unread")),
        "last_scheduled_run": doc.get("last_scheduled_run"),
        "pending_approval_count": int(doc.get("pending_approval_count") or 0),
        "execution_location": str(doc.get("execution_location") or "server"),
        "runtime_preset_id": str(doc.get("runtime_preset_id") or "askai-enterprise"),
        "code_project": doc.get("code_project"),
    }


async def _attach_pending_approval_counts(
    db: Any,
    documents: List[Dict[str, Any]],
    *,
    main_id: str,
    user_id: str,
) -> None:
    by_id = {str(doc.get("_id")): doc for doc in documents if doc.get("_id") is not None}
    if not by_id:
        return
    pipeline = [
        {"$match": {
            "tenant_id": resolve_main_id(main_id),
            "user_id": str(user_id),
            "conversation_id": {"$in": list(by_id)},
            "status": "pending",
        }},
        {"$group": {"_id": "$conversation_id", "count": {"$sum": 1}}},
    ]
    async for row in db.enterprise_tool_approvals.aggregate(pipeline):
        target = by_id.get(str(row.get("_id") or ""))
        if target is not None:
            target["pending_approval_count"] = int(row.get("count") or 0)


def _build_match_snippet(text: str, query: str, radius: int = 72) -> str:
    source = str(text or "").strip()
    needle = str(query or "").strip()
    if not source:
        return ""
    if not needle:
        return source[: radius * 2].strip()
    lower_source = source.lower()
    lower_needle = needle.lower()
    idx = lower_source.find(lower_needle)
    if idx < 0:
        return source[: radius * 2].strip()
    start = max(0, idx - radius)
    end = min(len(source), idx + len(needle) + radius)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(source) else ""
    return f"{prefix}{source[start:end].strip()}{suffix}"


async def _next_seq(db, session_id: ObjectId, user_id: str, main_id: str = "default") -> int:
    last = await db.chat_messages.find_one(
        add_main_scope({"session_id": session_id, "user_id": str(user_id)}, main_id),
        sort=[("seq", -1), ("created_at", -1)],
    )
    if not last:
        return 1
    try:
        return int(last.get("seq") or 0) + 1
    except Exception:
        return 1


def _extract_latest_artifact_ref_from_messages(messages: List[MessageIn]) -> Optional[Dict[str, Any]]:
    for m in reversed(messages or []):
        docs = list(m.documents or [])
        if not docs:
            continue
        md_doc = next((d for d in docs if isinstance(d, dict) and str(d.get("type") or "").lower() in {"md", "markdown"}), None)
        target = md_doc or next((d for d in docs if isinstance(d, dict) and d.get("object_path")), None)
        if not isinstance(target, dict):
            continue
        object_path = str(target.get("object_path") or "").strip()
        url = str(target.get("url") or "").strip()
        if not object_path and not url:
            continue
        return {
            "type": str(target.get("type") or ""),
            "object_path": object_path,
            "url": url,
            "filename": str(target.get("filename") or ""),
            "title": str(target.get("title") or ""),
            "updated_at": datetime.utcnow(),
        }
    return None


def _looks_like_document_message(message: MessageIn) -> bool:
    if str(message.role or "").strip().lower() != "assistant":
        return False
    content = str(message.content or "").strip()
    docs = list(message.documents or [])
    return bool(len(content) >= 180 or docs)


def _looks_like_reader_facing_document_content(content: str) -> bool:
    text = str(content or "").strip()
    if len(text) < 120:
        return False
    lines = [line.strip() for line in text.splitlines() if str(line or "").strip()]
    if not lines:
        return False
    has_heading = any(line.startswith("#") or (line.startswith("**") and line.endswith("**")) for line in lines[:12])
    has_paragraph = any(len(line) >= 40 and not line.startswith("![") for line in lines)
    return has_paragraph and (has_heading or len(lines) >= 3)


def _derive_document_title(content: str, docs: List[dict]) -> str:
    for doc in list(docs or []):
        if not isinstance(doc, dict):
            continue
        title = str(doc.get("title") or doc.get("filename") or doc.get("name") or "").strip()
        if title:
            return title[:160]
    text = str(content or "").strip()
    if not text:
        return ""
    first = next((line.strip() for line in text.splitlines() if str(line or "").strip()), "")
    first = first.lstrip("#").strip().strip("*").strip()
    return first[:160]


def _build_active_document_from_messages(
    messages: List[MessageIn],
    *,
    previous_active: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    latest = next((m for m in reversed(list(messages or [])) if _looks_like_document_message(m)), None)
    if latest is None:
        return previous_active
    previous = dict(previous_active or {})
    previous_id = str(previous.get("document_id") or "").strip()
    previous_version = int(previous.get("version") or 0)
    content = str(latest.content or "").strip()
    if not _looks_like_reader_facing_document_content(content):
        return previous_active
    docs = [dict(d) for d in list(latest.documents or []) if isinstance(d, dict)]
    md_doc = next((d for d in docs if str(d.get("type") or "").strip().lower() in {"md", "markdown"}), None)
    target = md_doc or next((d for d in docs if d.get("object_path") or d.get("url")), None) or {}
    return {
        "document_id": previous_id or f"doc_{uuid4().hex[:12]}",
        "version": previous_version + 1 if previous_id else 1,
        "title": _derive_document_title(content, docs),
        "content": content,
        "content_preview": content[:1200],
        "type": str(target.get("type") or "markdown").strip() or "markdown",
        "object_path": str(target.get("object_path") or "").strip(),
        "url": str(target.get("url") or "").strip(),
        "updated_at": datetime.utcnow(),
    }


def _make_version_entry(doc: Dict[str, Any], version: int) -> Dict[str, Any]:
    return {
        "version": int(version or 1),
        "title": str(doc.get("title") or "").strip(),
        "content": str(doc.get("content") or "").strip(),
        "content_preview": str(doc.get("content_preview") or "")[:600],
        "updated_at": doc.get("updated_at") or datetime.utcnow(),
        "object_path": str(doc.get("object_path") or "").strip(),
        "url": str(doc.get("url") or "").strip(),
        "type": str(doc.get("type") or "markdown").strip() or "markdown",
    }


async def _latest_user_request_from_db(db, session_id: ObjectId, user_id: str, main_id: str = "default") -> str:
    row = await db.chat_messages.find_one(
        add_main_scope({"session_id": session_id, "user_id": str(user_id), "role": "user"}, main_id),
        sort=[("seq", -1), ("created_at", -1)],
    )
    return str((row or {}).get("content") or "").strip()


async def _resolve_document_registry_update(
    *,
    latest_user_request: str,
    latest_document: Dict[str, Any],
    previous_registry: List[Dict[str, Any]],
    previous_active_id: str,
) -> Dict[str, Any]:
    doc = dict(latest_document or {})
    registry = [dict(item) for item in list(previous_registry or []) if isinstance(item, dict)]
    if not doc:
        return {"registry": registry, "active_document_id": previous_active_id}
    if not _looks_like_reader_facing_document_content(str(doc.get("content") or "")):
        return {"registry": registry, "active_document_id": previous_active_id}
    if not registry:
        doc_id = str(doc.get("document_id") or f"doc_{uuid4().hex[:12]}").strip()
        doc["document_id"] = doc_id
        doc["version"] = 1
        doc["versions"] = [_make_version_entry(doc, 1)]
        return {"registry": [doc], "active_document_id": doc_id}

    payload = {
        "latest_user_request": str(latest_user_request or "").strip(),
        "latest_document_preview": str(doc.get("content_preview") or doc.get("content") or "")[:1200],
        "active_document_id": str(previous_active_id or "").strip(),
        "candidates": [
            {
                "document_id": str(item.get("document_id") or "").strip(),
                "title": str(item.get("title") or "").strip(),
                "version": int(item.get("version") or 0),
                "content_preview": str(item.get("content_preview") or "")[:600],
            }
            for item in registry[-8:]
        ],
    }
    system = (
        "You maintain a session-level document registry.\n"
        "Return strict JSON only with fields:\n"
        "{\"action\":\"update_existing|create_new\","
        "\"target_document_id\":\"doc_xxx|NEW\","
        "\"reason\":\"...\"}\n"
        "Guidance:\n"
        "- update_existing: the latest assistant document is a new version or incremental update of an existing document.\n"
        "- create_new: the latest assistant document is a distinct new document topic/deliverable.\n"
        "- Prefer update_existing for revisions, exports, added images, retitles, compressions, or section patches of an existing document.\n"
        "- Prefer create_new only when the user clearly started a different document topic."
    )
    action = "update_existing"
    target_document_id = str(previous_active_id or "").strip() or "NEW"
    try:
        llm = get_llm_client(streaming=False, stage="intent_routing")
        resp = await llm.ainvoke(
            [Message(role=Role.SYSTEM, content=system), Message(role=Role.USER, content=str(payload).replace("'", '"'))]
        )
        raw = str(getattr(resp, "content", "") or "").strip()
        data = raw.replace("```json", "").replace("```", "").strip()
        import json as _json
        parsed = _json.loads(data)
        action = str(parsed.get("action") or action).strip()
        target_document_id = str(parsed.get("target_document_id") or target_document_id).strip() or target_document_id
    except Exception:
        pass

    if action == "create_new" or target_document_id == "NEW":
        doc_id = f"doc_{uuid4().hex[:12]}"
        doc["document_id"] = doc_id
        doc["version"] = 1
        doc["versions"] = [_make_version_entry(doc, 1)]
        registry.append(doc)
        return {"registry": registry[-12:], "active_document_id": doc_id}

    matched = False
    for idx, item in enumerate(registry):
        if str(item.get("document_id") or "").strip() != target_document_id:
            continue
        updated = dict(item)
        updated.update(doc)
        updated["document_id"] = target_document_id
        updated["version"] = int(item.get("version") or 0) + 1
        prev_versions = [dict(v) for v in list(item.get("versions") or []) if isinstance(v, dict)]
        prev_versions.append(_make_version_entry(updated, int(updated["version"])))
        updated["versions"] = prev_versions[-12:]
        registry[idx] = updated
        matched = True
        break
    if not matched:
        doc["document_id"] = target_document_id
        doc["version"] = 1
        doc["versions"] = [_make_version_entry(doc, 1)]
        registry.append(doc)
    return {"registry": registry[-12:], "active_document_id": target_document_id}


def _clean_message_images_for_storage(images: Optional[List[Any]]) -> List[Dict[str, Any]]:
    if not images:
        return []
    cleaned = []
    for img in images:
        item = img.model_dump() if hasattr(img, "model_dump") else dict(img)
        # Drop volatile signature
        item.pop("signed_url", None)
        # Strip query parameters from the main URL to store only the raw path
        url = item.get("url")
        if url and "?" in url:
            item["url"] = url.split("?")[0]
        cleaned.append(item)
    return cleaned


def _build_context_summary_from_messages(rows: List[Dict[str, Any]]) -> str:
    return context_compactor.heuristic_summary(rows)


async def _maybe_compact_session_messages(db, *, session_id: ObjectId, user_id: str, main_id: str = "default") -> None:
    cursor = db.chat_messages.find(
        add_main_scope({
            "session_id": session_id,
            "user_id": str(user_id),
            "message_type": {"$ne": "context_summary"},
            "compacted": {"$ne": True},
        }, main_id)
    ).sort("seq", 1)
    rows = await cursor.to_list(length=1000)
    if len(rows) <= COMPACTION_TRIGGER_MESSAGES:
        return
    to_compact = rows[:-COMPACTION_KEEP_RECENT]
    if not to_compact:
        return
    compaction_id = f"cmp_{uuid4().hex[:12]}"
    compaction = await context_compactor.compact_messages(
        to_compact,
        output_spec={"user_id": str(user_id), "main_id": resolve_main_id(main_id), "session_id": str(session_id)},
    )
    summary_text = compaction.summary or _build_context_summary_from_messages(to_compact)
    if compaction.memories:
        await project_memory_service.upsert_memories(
            user_id=str(user_id),
            main_id=resolve_main_id(main_id),
            project_id="default",
            memories=compaction.memories,
            source=f"session_compaction:{compaction_id}",
        )
    ids = [r.get("_id") for r in to_compact if r.get("_id")]
    if ids:
        await db.chat_messages.update_many(
            {"_id": {"$in": ids}},
            {"$set": {"compacted": True, "compaction_id": compaction_id, "compacted_at": datetime.utcnow()}},
        )
    start_seq = int(to_compact[0].get("seq") or 0)
    end_seq = int(to_compact[-1].get("seq") or 0)
    next_seq = await _next_seq(db, session_id, user_id, main_id)
    await db.chat_messages.insert_one(
        {
            "session_id": session_id,
            "user_id": str(user_id),
            "main_id": resolve_main_id(main_id),
            "role": "system",
            "content": summary_text,
            "plan": None,
            "progress": None,
            "documents": [],
            "images": [],
            "created_at": datetime.utcnow(),
            "seq": next_seq,
            "message_type": "context_summary",
            "summary_source": compaction.source,
            "compacted": False,
            "compaction_id": compaction_id,
            "covers": {"start_seq": start_seq, "end_seq": end_seq},
        }
    )
    await db.chat_sessions.update_one(
        {"_id": session_id},
        {"$set": {"last_compaction_at": datetime.utcnow(), "latest_compaction_id": compaction_id}},
    )


@router.post("/sessions", response_model=ApiResponse)
async def create_session(
    payload: SessionCreate,
    authorization: str | None = Header(default=None),
) -> ApiResponse:
    user_id, main_id = await _authorized_scope(
        authorization, claimed_user_id=str(payload.user_id), claimed_main_id=payload.main_id
    )
    session_doc = await session_persistence_service.create_session(
        user_id=user_id,
        main_id=main_id,
        title=payload.title or "New Chat",
        messages=payload.messages or [],
    )
    return ApiResponse(code=0, message="success", data=_serialize_session(session_doc))


@router.get("/sessions", response_model=ApiResponse)
async def list_sessions(
    user_id: str = Query(..., alias="userId"),
    main_id: str = Query("default", alias="mainId"),
    main_id_snake: Optional[str] = Query(None, alias="main_id"),
    paged: bool = Query(False),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    authorization: str | None = Header(default=None),
) -> ApiResponse:
    t0 = time.perf_counter()
    main_id = main_id_snake or main_id
    user_id, main_id = await _authorized_scope(
        authorization, claimed_user_id=user_id, claimed_main_id=main_id
    )
    log_print(
        "[perf][sessions] list_sessions:start user_id=%s main_id=%s paged=%s limit=%s offset=%s"
        % (str(user_id), resolve_main_id(main_id), bool(paged), int(limit), int(offset)),
        flush=True,
    )
    db = get_db()
    projection = {
        "user_id": 1,
        "main_id": 1,
        "title": 1,
        "created_at": 1,
        "updated_at": 1,
        "last_message_at": 1,
        "last_message_preview": 1,
        "message_count": 1,
        "latest_artifact_ref": 1,
        "active_document_id": 1,
        "document_count": 1,
        "active_run": 1,
        "scheduled_unread": 1,
        "last_scheduled_run": 1,
    }
    base_cursor = (
        db.chat_sessions.find(add_main_scope({"user_id": str(user_id)}, main_id), projection)
        .sort([("updated_at", -1), ("_id", -1)])
        .hint([("user_id", 1), ("updated_at", -1), ("_id", -1)])
    )

    if not paged:
        documents = []
        async for doc in base_cursor:
            documents.append(doc)
        await _attach_pending_approval_counts(
            db, documents, main_id=main_id, user_id=user_id
        )
        await attach_session_runtime_contexts(
            db, documents, tenant_id=main_id, user_id=user_id
        )
        sessions = [SessionSummary(**_serialize_session_summary(doc)) for doc in documents]
        duration_ms = int((time.perf_counter() - t0) * 1000)
        log_print(
            "[perf][sessions] list_sessions:done user_id=%s main_id=%s paged=false count=%s duration_ms=%s"
            % (str(user_id), resolve_main_id(main_id), len(sessions), duration_ms),
            flush=True,
        )
        return ApiResponse(code=0, message="success", data=sessions)

    cursor = base_cursor.skip(offset).limit(limit + 1)
    documents = []
    async for doc in cursor:
        documents.append(doc)
    has_more = len(documents) > limit
    if has_more:
        documents = documents[:limit]
    await _attach_pending_approval_counts(
        db, documents, main_id=main_id, user_id=user_id
    )
    await attach_session_runtime_contexts(
        db, documents, tenant_id=main_id, user_id=user_id
    )
    sessions = [SessionSummary(**_serialize_session_summary(doc)) for doc in documents]
    duration_ms = int((time.perf_counter() - t0) * 1000)
    log_print(
        "[perf][sessions] list_sessions:done user_id=%s main_id=%s paged=true count=%s has_more=%s duration_ms=%s"
        % (str(user_id), resolve_main_id(main_id), len(sessions), bool(has_more), duration_ms),
        flush=True,
    )
    return ApiResponse(
        code=0,
        message="success",
        data={
            "items": sessions,
            "offset": offset,
            "limit": limit,
            "has_more": has_more,
        },
    )


@router.get("/sessions/search", response_model=ApiResponse)
async def search_sessions(
    user_id: str = Query(..., alias="userId"),
    main_id: str = Query("default", alias="mainId"),
    main_id_snake: Optional[str] = Query(None, alias="main_id"),
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    authorization: str | None = Header(default=None),
) -> ApiResponse:
    db = get_db()
    main_id = main_id_snake or main_id
    user_id, main_id = await _authorized_scope(
        authorization, claimed_user_id=user_id, claimed_main_id=main_id
    )
    query_text = str(q or "").strip()
    if not query_text:
        return ApiResponse(
            code=0,
            message="success",
            data={"items": [], "offset": offset, "limit": limit, "has_more": False},
        )

    regex = re.compile(re.escape(query_text), re.IGNORECASE)
    projection = {
        "user_id": 1,
        "main_id": 1,
        "title": 1,
        "created_at": 1,
        "updated_at": 1,
        "last_message_at": 1,
        "last_message_preview": 1,
        "message_count": 1,
        "latest_artifact_ref": 1,
        "active_document_id": 1,
        "document_count": 1,
        "active_run": 1,
        "scheduled_unread": 1,
        "last_scheduled_run": 1,
    }

    candidates: Dict[str, Dict[str, Any]] = {}

    async for doc in db.chat_sessions.find(
        add_main_scope({
            "user_id": str(user_id),
            "$or": [
                {"title": {"$regex": regex}},
                {"last_message_preview": {"$regex": regex}},
            ],
        }, main_id),
        projection,
    ).sort("updated_at", -1).limit(max(limit * 4, 40)):
        sid = str(doc.get("_id"))
        snippets: List[str] = []
        match_type = "title"
        score = 120
        title = str(doc.get("title") or "")
        preview = str(doc.get("last_message_preview") or "")
        if query_text.lower() in title.lower():
            snippets.append(_build_match_snippet(title, query_text, radius=36))
        elif preview:
            snippets.append(_build_match_snippet(preview, query_text))
            match_type = "preview"
            score = 80
        candidates[sid] = {
            "session": doc,
            "snippets": snippets[:3],
            "match_type": match_type,
            "matched_message_count": 0,
            "score": score,
        }

    message_limit = max((offset + limit) * 12, 120)
    async for msg in db.chat_messages.find(
        add_main_scope({
            "user_id": str(user_id),
            "message_type": {"$ne": "context_summary"},
            "content": {"$regex": regex},
        }, main_id),
        {
            "session_id": 1,
            "content": 1,
            "created_at": 1,
        },
    ).sort("created_at", -1).limit(message_limit):
        raw_session_id = msg.get("session_id")
        if not raw_session_id:
            continue
        sid = str(raw_session_id)
        entry = candidates.get(sid)
        if entry is None:
            session_doc = await db.chat_sessions.find_one(
                add_main_scope({"_id": raw_session_id, "user_id": str(user_id)}, main_id),
                projection,
            )
            if not session_doc:
                continue
            entry = {
                "session": session_doc,
                "snippets": [],
                "match_type": "message",
                "matched_message_count": 0,
                "score": 0,
            }
            candidates[sid] = entry
        entry["matched_message_count"] = int(entry.get("matched_message_count") or 0) + 1
        snippets = list(entry.get("snippets") or [])
        snippet = _build_match_snippet(str(msg.get("content") or ""), query_text)
        if snippet and snippet not in snippets and len(snippets) < 3:
            snippets.append(snippet)
        entry["snippets"] = snippets
        if entry.get("match_type") not in {"title", "preview"}:
            entry["match_type"] = "message"
        entry["score"] = int(entry.get("score") or 0) + (60 if entry["matched_message_count"] == 1 else 10)

    ordered = sorted(
        candidates.values(),
        key=lambda item: (
            int(item.get("score") or 0),
            item.get("session", {}).get("updated_at") or datetime.min,
        ),
        reverse=True,
    )
    paged = ordered[offset : offset + limit + 1]
    has_more = len(paged) > limit
    if has_more:
        paged = paged[:limit]

    await _attach_pending_approval_counts(
        db,
        [item.get("session") or {} for item in paged],
        main_id=main_id,
        user_id=user_id,
    )
    await attach_session_runtime_contexts(
        db,
        [item.get("session") or {} for item in paged],
        tenant_id=main_id,
        user_id=user_id,
    )

    items = []
    for item in paged:
        session_doc = item.get("session") or {}
        payload = _serialize_session_summary(session_doc)
        payload["match_type"] = str(item.get("match_type") or "message")
        payload["snippets"] = list(item.get("snippets") or [])[:3]
        payload["matched_message_count"] = int(item.get("matched_message_count") or 0)
        items.append(SessionSearchResult(**payload))

    return ApiResponse(
        code=0,
        message="success",
        data={
            "items": items,
            "offset": offset,
            "limit": limit,
            "has_more": has_more,
        },
    )


@router.get("/sessions/{session_id}", response_model=ApiResponse)
async def get_session(
    session_id: str,
    user_id: str = Query(..., alias="userId"),
    main_id: str = Query("default", alias="mainId"),
    main_id_snake: Optional[str] = Query(None, alias="main_id"),
    include_context_summary: bool = Query(False, alias="includeContextSummary"),
    authorization: str | None = Header(default=None),
) -> ApiResponse:
    db = get_db()
    try:
        oid = ObjectId(session_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid session id") from exc

    user_id, main_id = await _authorized_scope(
        authorization,
        claimed_user_id=user_id,
        claimed_main_id=main_id_snake or main_id,
    )
    session_doc = await db.chat_sessions.find_one(add_main_scope({"_id": oid, "user_id": str(user_id)}, main_id))
    if not session_doc:
        raise HTTPException(status_code=404, detail="Session not found")
    await _attach_pending_approval_counts(
        db, [session_doc], main_id=main_id, user_id=user_id
    )
    await attach_session_runtime_contexts(
        db, [session_doc], tenant_id=main_id, user_id=user_id
    )

    messages = []
    query: Dict[str, Any] = {
        "session_id": oid,
        "user_id": str(user_id),
    }
    query = add_main_scope(query, main_id)
    if not include_context_summary:
        # Frontend should display original dialogue turns only.
        # Context summaries are runtime-only compression artifacts.
        query["message_type"] = {"$ne": "context_summary"}

    uploader: Optional[AliyunOSSUploader] = None

    def _sign_oss_paths_in_events(events: Any, uploader_obj: AliyunOSSUploader) -> None:
        """Walk persisted execution events and attach a fresh signed_url to
        every ``{"_oss_object_path": "..."}`` descriptor so the frontend can
        display screenshots from historical sessions. In-place mutation."""
        if isinstance(events, dict):
            op = events.get("_oss_object_path")
            if isinstance(op, str) and op:
                try:
                    events["signed_url"] = uploader_obj.sign_url(op)
                except Exception as exc:
                    log_print(f"[sessions] failed to sign event screenshot {op}: {exc}", flush=True)
            for v in events.values():
                if isinstance(v, (dict, list)):
                    _sign_oss_paths_in_events(v, uploader_obj)
        elif isinstance(events, list):
            for item in events:
                if isinstance(item, (dict, list)):
                    _sign_oss_paths_in_events(item, uploader_obj)

    # Prefer finalized V3 logs. Older records are imported at this read boundary
    # so the client still receives one V3 contract.
    exec_events_by_msg_id: Dict[str, list] = {}
    try:
        from app.historical.legacy_execution_logs import LegacyExecutionLogStore
        from app.infrastructure.execution_events.persistence import ExecutionV3Store
        exec_store = LegacyExecutionLogStore(db)
        exec_events_by_msg_id = await exec_store.get_events_for_session(str(oid), main_id=main_id)
        v3_events = await ExecutionV3Store(db).get_events_for_session(str(oid), main_id=main_id)
        for message_id, events in v3_events.items():
            exec_events_by_msg_id[message_id] = events
    except Exception as exc:
        log_print(f"[sessions] execution_events fetch failed: {exc}", flush=True)

    async for msg in db.chat_messages.find(query).sort("seq", 1):
        msg_images = msg.get("images") or []
        content = msg.get("content") or ""

        has_refreshable_content = bool(content and ("![" in content or "<img" in content or "http" in content))
        if msg_images or has_refreshable_content:
            if uploader is None:
                uploader = AliyunOSSUploader()

            # Re-sign specific images in the 'images' field
            for img in msg_images:
                if isinstance(img, dict) and img.get("object_path"):
                    try:
                        img["signed_url"] = uploader.sign_url(img["object_path"])
                    except Exception as e:
                        log_print(f"[sessions] Failed to re-sign image {img['object_path']}: {e}")

            # Refresh file URLs embedded in markdown when the active backend requires it.
            if content:
                content = uploader.refresh_markdown_urls(content)

        msg_id_val = str(msg.get("message_id") or "")
        events_for_msg = exec_events_by_msg_id.get(msg_id_val) if msg_id_val else None
        stored_events_for_msg = msg.get("execution_events") if isinstance(msg.get("execution_events"), list) else None
        if stored_events_for_msg and not events_for_msg:
            events_for_msg = stored_events_for_msg
        if events_for_msg:
            events_for_msg = normalize_execution_history(events_for_msg)

        if events_for_msg:
            if uploader is None:
                try:
                    uploader = AliyunOSSUploader()
                except Exception as exc:
                    log_print(f"[sessions] OSS uploader init failed, screenshots won't be signed: {exc}", flush=True)
                    uploader = None
            if uploader is not None:
                _sign_oss_paths_in_events(events_for_msg, uploader)

        messages.append(
            MessageIn(
                role=msg.get("role"),
                content=content,
                plan=msg.get("plan"),
                progress=msg.get("progress"),
                documents=msg.get("documents"),
                images=msg_images,
                evidence_bundles=msg.get("evidence_bundles"),
                message_id=msg_id_val or None,
                execution_events=events_for_msg or None,
                trigger_source=msg.get("trigger_source"),
                scheduled_job_id=msg.get("scheduled_job_id"),
                scheduled_run_id=msg.get("scheduled_run_id"),
                created_at=msg.get("created_at"),
            )
        )
    data = _serialize_session(session_doc)
    if session_doc.get("scheduled_unread"):
        await db.chat_sessions.update_one(
            add_main_scope({"_id": oid, "user_id": str(user_id)}, main_id),
            {"$set": {"scheduled_unread": False}},
        )
    return ApiResponse(
        code=0,
        message="success",
        data=SessionDetail(**data, messages=messages).model_dump(),
    )


@router.patch("/sessions/{session_id}", response_model=ApiResponse)
async def update_session(
    session_id: str,
    payload: SessionUpdate,
    authorization: str | None = Header(default=None),
) -> ApiResponse:
    db = get_db()
    try:
        oid = ObjectId(session_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid session id") from exc

    title = str(payload.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")

    user_id, main_id = await _authorized_scope(
        authorization, claimed_user_id=str(payload.user_id), claimed_main_id=payload.main_id
    )
    result = await db.chat_sessions.update_one(
        add_main_scope({"_id": oid, "user_id": user_id}, main_id),
        {
            "$set": {
                "title": title[:160],
            }
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")

    session_doc = await db.chat_sessions.find_one(add_main_scope({"_id": oid, "user_id": user_id}, main_id))
    if not session_doc:
        raise HTTPException(status_code=404, detail="Session not found")
    return ApiResponse(code=0, message="success", data=SessionSummary(**_serialize_session_summary(session_doc)).model_dump())


@router.delete("/sessions/{session_id}", response_model=ApiResponse)
async def delete_session(
    session_id: str,
    user_id: str = Query(..., alias="userId"),
    main_id: str = Query("default", alias="mainId"),
    main_id_snake: Optional[str] = Query(None, alias="main_id"),
    authorization: str | None = Header(default=None),
) -> ApiResponse:
    db = get_db()
    try:
        oid = ObjectId(session_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid session id") from exc

    user_id, main_id = await _authorized_scope(
        authorization,
        claimed_user_id=user_id,
        claimed_main_id=main_id_snake or main_id,
    )
    session_doc = await db.chat_sessions.find_one(add_main_scope({"_id": oid, "user_id": str(user_id)}, main_id), {"_id": 1})
    if not session_doc:
        raise HTTPException(status_code=404, detail="Session not found")

    from app.dsh_runtime.application import dsh_runtime_application
    await dsh_runtime_application.require_chat().dispose_conversation(
        str(oid), tenant_id=main_id, user_id=user_id
    )
    await db.chat_sessions.delete_one(add_main_scope({"_id": oid, "user_id": str(user_id)}, main_id))
    await db.chat_messages.delete_many(add_main_scope({"session_id": oid, "user_id": str(user_id)}, main_id))
    try:
        await db.execution_logs.delete_many(add_main_scope({"session_id": str(oid), "user_id": str(user_id)}, main_id))
    except Exception as exc:
        log_print(f"[sessions] delete execution_logs failed: {exc}", flush=True)

    return ApiResponse(
        code=0,
        message="success",
        data={"id": str(oid)},
    )


@router.post("/sessions/{session_id}/messages", response_model=ApiResponse)
async def append_messages(
    session_id: str,
    payload: MessageAppend,
    authorization: str | None = Header(default=None),
) -> ApiResponse:
    try:
        ObjectId(session_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid session id") from exc
    if not payload.messages:
        raise HTTPException(status_code=400, detail="No messages to append")
    user_id, main_id = await _authorized_scope(
        authorization, claimed_user_id=str(payload.user_id), claimed_main_id=payload.main_id
    )
    try:
        session_doc = await session_persistence_service.append_messages(
            session_id=session_id,
            user_id=user_id,
            main_id=main_id,
            messages=payload.messages or [],
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
    return ApiResponse(code=0, message="success", data=_serialize_session(session_doc))
