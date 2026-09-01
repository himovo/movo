from __future__ import annotations
from app.infrastructure.observability.config import log_print

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from bson import ObjectId

from app.context_engine.compactor import context_compactor
from app.context_engine.project_memory import project_memory_service
from app.core.db import get_db
from app.core.tenant import add_main_scope, resolve_main_id
from app.llm.factory import get_llm_client
from app.llm.types import Message, Role


COMPACTION_TRIGGER_MESSAGES = 40
COMPACTION_KEEP_RECENT = 20


def _normalize_message(message: Any) -> Dict[str, Any]:
    if hasattr(message, "model_dump"):
        message = message.model_dump()
    elif not isinstance(message, dict):
        message = {
            "role": getattr(message, "role", ""),
            "content": getattr(message, "content", ""),
            "plan": getattr(message, "plan", None),
            "progress": getattr(message, "progress", None),
            "documents": getattr(message, "documents", None),
            "images": getattr(message, "images", None),
            "evidence_bundles": getattr(message, "evidence_bundles", None),
            "execution_events": getattr(message, "execution_events", None),
            "message_id": getattr(message, "message_id", None),
        }
    out = dict(message or {})
    out["role"] = str(out.get("role") or "").strip().lower()
    out["content"] = str(out.get("content") or "")
    out["documents"] = [dict(d) for d in list(out.get("documents") or []) if isinstance(d, dict)]
    out["images"] = [dict(i) for i in list(out.get("images") or []) if isinstance(i, dict)]
    raw_evidence = out.get("evidence_bundles")
    if raw_evidence is None:
        raw_evidence = out.get("evidenceBundles")
    out["evidence_bundles"] = [dict(item) for item in list(raw_evidence or []) if isinstance(item, dict)]
    raw_events = out.get("execution_events")
    if raw_events is None:
        raw_events = out.get("executionEvents")
    out["execution_events"] = [dict(item) for item in list(raw_events or []) if isinstance(item, dict)]
    out["trigger_source"] = str(out.get("trigger_source") or "").strip() or None
    out["scheduled_job_id"] = str(out.get("scheduled_job_id") or "").strip() or None
    out["scheduled_run_id"] = str(out.get("scheduled_run_id") or "").strip() or None
    return out


async def _next_seq(db: Any, session_id: ObjectId, user_id: str, main_id: str = "default") -> int:
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


def extract_latest_artifact_ref_from_messages(messages: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for m in reversed(messages or []):
        docs = list(m.get("documents") or [])
        if not docs:
            continue
        md_doc = next((d for d in docs if isinstance(d, dict) and str(d.get("type") or d.get("kind") or "").lower() in {"md", "markdown"}), None)
        target = md_doc or next((d for d in docs if isinstance(d, dict) and d.get("object_path")), None)
        if not isinstance(target, dict):
            continue
        object_path = str(target.get("object_path") or "").strip()
        url = str(target.get("url") or "").strip()
        if not object_path and not url:
            continue
        return {
            "type": str(target.get("type") or target.get("kind") or ""),
            "object_path": object_path,
            "url": url,
            "filename": str(target.get("filename") or ""),
            "title": str(target.get("title") or ""),
            "updated_at": datetime.utcnow(),
        }
    return None


def _looks_like_document_message(message: Dict[str, Any]) -> bool:
    if str(message.get("role") or "").strip().lower() != "assistant":
        return False
    content = str(message.get("content") or "").strip()
    docs = list(message.get("documents") or [])
    return bool(len(content) >= 180 or docs)


def looks_like_reader_facing_document_content(content: str) -> bool:
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


def build_active_document_from_messages(
    messages: List[Dict[str, Any]],
    *,
    previous_active: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    latest = next((m for m in reversed(list(messages or [])) if _looks_like_document_message(m)), None)
    if latest is None:
        return previous_active
    previous = dict(previous_active or {})
    previous_id = str(previous.get("document_id") or "").strip()
    previous_version = int(previous.get("version") or 0)
    content = str(latest.get("content") or "").strip()
    if not looks_like_reader_facing_document_content(content):
        return previous_active
    docs = [dict(d) for d in list(latest.get("documents") or []) if isinstance(d, dict)]
    md_doc = next((d for d in docs if str(d.get("type") or d.get("kind") or "").strip().lower() in {"md", "markdown"}), None)
    target = md_doc or next((d for d in docs if d.get("object_path") or d.get("url")), None) or {}
    return {
        "document_id": previous_id or f"doc_{uuid4().hex[:12]}",
        "version": previous_version + 1 if previous_id else 1,
        "title": _derive_document_title(content, docs),
        "content": content,
        "content_preview": content[:1200],
        "type": str(target.get("type") or target.get("kind") or "markdown").strip() or "markdown",
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


async def _latest_user_request_from_db(db: Any, session_id: ObjectId, user_id: str, main_id: str = "default") -> str:
    row = await db.chat_messages.find_one(
        add_main_scope({"session_id": session_id, "user_id": str(user_id), "role": "user"}, main_id),
        sort=[("seq", -1), ("created_at", -1)],
    )
    return str((row or {}).get("content") or "").strip()


async def resolve_document_registry_update(
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
    if not looks_like_reader_facing_document_content(str(doc.get("content") or "")):
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
            [Message(role=Role.SYSTEM, content=system), Message(role=Role.USER, content=json.dumps(payload, ensure_ascii=False))]
        )
        raw = str(getattr(resp, "content", "") or "").strip()
        data = raw.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(data)
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


def clean_message_images_for_storage(images: Optional[List[Any]]) -> List[Dict[str, Any]]:
    if not images:
        return []
    cleaned = []
    for img in images:
        item = img.model_dump() if hasattr(img, "model_dump") else dict(img)
        item.pop("signed_url", None)
        url = item.get("url")
        if url and "?" in url:
            item["url"] = url.split("?", 1)[0]
        cleaned.append(item)
    return cleaned


def _build_context_summary_from_messages(rows: List[Dict[str, Any]]) -> str:
    return context_compactor.heuristic_summary(rows)


async def maybe_compact_session_messages(db: Any, *, session_id: ObjectId, user_id: str, main_id: str = "default") -> None:
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


class SessionPersistenceService:
    async def create_session(
        self,
        *,
        user_id: str,
        main_id: str = "default",
        title: str = "New Chat",
        messages: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        db = get_db()
        now = datetime.utcnow()
        mid = resolve_main_id(main_id)
        normalized = [_normalize_message(m) for m in list(messages or [])]
        last_message = normalized[-1]["content"] if normalized else None
        last_message_at = now if normalized else None
        session_doc: Dict[str, Any] = {
            "user_id": str(user_id),
            "main_id": mid,
            "title": title or "New Chat",
            "created_at": now,
            "updated_at": now,
            "last_message_at": last_message_at,
            "last_message_preview": (last_message[:120] if last_message else None),
            "message_count": len(normalized),
            "latest_artifact_ref": extract_latest_artifact_ref_from_messages(normalized),
            "active_document": build_active_document_from_messages(normalized),
            "active_document_id": "",
            "document_registry": [],
        }
        active_document = dict(session_doc.get("active_document") or {})
        if active_document:
            resolved = await resolve_document_registry_update(
                latest_user_request=next((str(m.get("content") or "").strip() for m in reversed(normalized) if str(m.get("role") or "").lower() == "user"), ""),
                latest_document=active_document,
                previous_registry=[],
                previous_active_id="",
            )
            session_doc["document_registry"] = list(resolved.get("registry") or [])
            session_doc["active_document_id"] = str(resolved.get("active_document_id") or "").strip()
            selected = next(
                (dict(item) for item in list(session_doc["document_registry"] or []) if str(item.get("document_id") or "").strip() == session_doc["active_document_id"]),
                active_document,
            )
            session_doc["active_document"] = selected
            session_doc["document_count"] = len(list(session_doc.get("document_registry") or []))
        result = await db.chat_sessions.insert_one(session_doc)
        session_id = result.inserted_id
        if normalized:
            message_docs = [
                self._message_doc(
                    session_id=session_id,
                    user_id=str(user_id),
                    main_id=mid,
                    message=m,
                    created_at=now,
                    seq=i + 1,
                )
                for i, m in enumerate(normalized)
            ]
            await db.chat_messages.insert_many(message_docs)
            await self._rekey_execution_logs(session_id=session_id, main_id=mid, messages=normalized)
        session_doc["_id"] = session_id
        return session_doc

    async def append_messages(
        self,
        *,
        session_id: str,
        user_id: str,
        main_id: str = "default",
        messages: List[Any],
    ) -> Dict[str, Any]:
        db = get_db()
        oid = ObjectId(str(session_id))
        mid = resolve_main_id(main_id)
        session_doc = await db.chat_sessions.find_one(add_main_scope({"_id": oid, "user_id": str(user_id)}, mid))
        if not session_doc:
            raise LookupError("Session not found")
        normalized = [_normalize_message(m) for m in list(messages or [])]
        if not normalized:
            raise ValueError("No messages to append")
        # Idempotency for service-side persistence and historical client retries.
        message_ids = [str(m.get("message_id") or "").strip() for m in normalized if str(m.get("message_id") or "").strip()]
        if message_ids:
            existing = await db.chat_messages.count_documents(
                add_main_scope({"session_id": oid, "user_id": str(user_id), "message_id": {"$in": message_ids}}, mid)
            )
            if existing >= len(message_ids):
                return session_doc

        now = datetime.utcnow()
        seq = await _next_seq(db, oid, str(user_id), mid)
        message_docs = [
            self._message_doc(
                session_id=oid,
                user_id=str(user_id),
                main_id=mid,
                message=m,
                created_at=now,
                seq=seq + i,
            )
            for i, m in enumerate(normalized)
        ]
        await db.chat_messages.insert_many(message_docs)
        await self._rekey_execution_logs(session_id=oid, main_id=mid, messages=normalized)

        last_message = normalized[-1]["content"]
        latest_artifact_ref = extract_latest_artifact_ref_from_messages(normalized)
        active_document = build_active_document_from_messages(normalized, previous_active=session_doc.get("active_document"))
        set_payload: Dict[str, Any] = {
            "updated_at": now,
            "last_message_at": now,
            "last_message_preview": last_message[:120],
        }
        if latest_artifact_ref:
            set_payload["latest_artifact_ref"] = latest_artifact_ref
        if active_document:
            latest_user_request = next(
                (str(m.get("content") or "").strip() for m in reversed(normalized) if str(m.get("role") or "").lower() == "user"),
                "",
            ) or await _latest_user_request_from_db(db, oid, str(user_id), mid)
            resolved = await resolve_document_registry_update(
                latest_user_request=latest_user_request,
                latest_document=active_document,
                previous_registry=list(session_doc.get("document_registry") or []),
                previous_active_id=str(session_doc.get("active_document_id") or "").strip(),
            )
            registry = list(resolved.get("registry") or [])
            active_document_id = str(resolved.get("active_document_id") or "").strip()
            selected = next(
                (dict(item) for item in registry if str(item.get("document_id") or "").strip() == active_document_id),
                active_document,
            )
            set_payload["document_registry"] = registry
            set_payload["active_document_id"] = active_document_id
            set_payload["active_document"] = selected
            set_payload["document_count"] = len(registry)
        await db.chat_sessions.update_one(
            add_main_scope({"_id": oid}, mid),
            {
                "$set": set_payload,
                "$inc": {"message_count": len(normalized)},
            },
        )
        await maybe_compact_session_messages(db, session_id=oid, user_id=str(user_id), main_id=mid)

        session_doc.update(
            {
                "updated_at": now,
                "last_message_at": now,
                "last_message_preview": last_message[:120],
                "message_count": session_doc.get("message_count", 0) + len(normalized),
            }
        )
        if latest_artifact_ref:
            session_doc["latest_artifact_ref"] = latest_artifact_ref
        if active_document:
            session_doc["document_registry"] = list(set_payload.get("document_registry") or session_doc.get("document_registry") or [])
            session_doc["active_document_id"] = str(set_payload.get("active_document_id") or session_doc.get("active_document_id") or "").strip()
            session_doc["active_document"] = dict(set_payload.get("active_document") or active_document)
            session_doc["document_count"] = len(list(session_doc.get("document_registry") or []))
        return session_doc

    @staticmethod
    def _message_doc(
        *,
        session_id: ObjectId,
        user_id: str,
        main_id: str,
        message: Dict[str, Any],
        created_at: datetime,
        seq: int,
    ) -> Dict[str, Any]:
        return {
            "session_id": session_id,
            "user_id": str(user_id),
            "main_id": resolve_main_id(main_id),
            "role": str(message.get("role") or ""),
            "content": str(message.get("content") or ""),
            "plan": message.get("plan"),
            "progress": message.get("progress"),
            "documents": message.get("documents") or [],
            "images": clean_message_images_for_storage(message.get("images") or []),
            "evidence_bundles": message.get("evidence_bundles") or [],
            "execution_events": message.get("execution_events") or [],
            "created_at": created_at,
            "seq": int(seq),
            "message_type": "normal",
            "compacted": False,
            "message_id": str(message.get("message_id") or "").strip() or None,
            "trigger_source": str(message.get("trigger_source") or "").strip() or None,
            "scheduled_job_id": str(message.get("scheduled_job_id") or "").strip() or None,
            "scheduled_run_id": str(message.get("scheduled_run_id") or "").strip() or None,
        }

    async def _rekey_execution_logs(self, *, session_id: ObjectId, main_id: str, messages: List[Dict[str, Any]]) -> None:
        message_ids = [str(m.get("message_id") or "").strip() for m in messages if str(m.get("message_id") or "").strip()]
        if not message_ids:
            return
        try:
            await get_db().execution_logs.update_many(
                {"message_id": {"$in": message_ids}, "session_id": {"$ne": str(session_id)}},
                {"$set": {"session_id": str(session_id), "main_id": resolve_main_id(main_id)}},
            )
        except Exception as exc:
            log_print(f"[session_persistence] rekey execution_logs failed: {exc}", flush=True)
        try:
            await get_db().execution_runs_v3.update_many(
                {"message_id": {"$in": message_ids}, "session_id": {"$ne": str(session_id)}},
                {"$set": {"session_id": str(session_id), "main_id": resolve_main_id(main_id)}},
            )
        except Exception as exc:
            log_print(f"[session_persistence] rekey execution_runs_v3 failed: {exc}", flush=True)


session_persistence_service = SessionPersistenceService()
