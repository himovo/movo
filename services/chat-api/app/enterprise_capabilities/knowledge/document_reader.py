"""Authorized, ordered reads of already parsed knowledge documents."""

from __future__ import annotations

from typing import Any

from app.core.db import get_db
from app.core.tenant import resolve_main_id
from app.product.extensions import get_product_extension
from app.services.personal_knowledge.access import PersonalKnowledgeAccessService


async def _resolve_document(*, tenant_id: str, user_id: str, scope: str, source_id: str, require_parsed: bool = True) -> dict[str, Any]:
    if scope == "personal":
        access = await PersonalKnowledgeAccessService().require_view(
            main_id=tenant_id, user_id=user_id, resource_id=source_id,
        )
        document_id = str(access.resource.get("processing_document_id") or access.resource.get("active_document_id") or "")
        if not document_id:
            raise LookupError("knowledge_document_not_ready")
        # Check access before opening the database. Besides avoiding unnecessary
        # work, this keeps revoked-resource checks independent of DB availability.
        db = get_db()
        document = await db.knowledge_documents.find_one({
            "_id": document_id, "main_id": tenant_id, "resource_id": source_id,
            "scope": "personal", "deleted_at": None,
        })
    elif scope == "organization":
        db = get_db()
        document_id = source_id
        document = await db.knowledge_documents.find_one({
            "_id": document_id, "main_id": tenant_id, "deleted_at": None,
            "$or": [{"scope": "organization"}, {"scope": {"$exists": False}}],
        })
        if document is not None:
            policy = get_product_extension().knowledge_access_policy
            if policy is not None:
                await policy.require_view(
                    main_id=tenant_id, user_id=user_id, document_id=document_id,
                )
    else:
        raise ValueError("knowledge_scope_invalid")
    if document is None:
        raise LookupError("knowledge_document_not_found")
    if require_parsed and str(document.get("parse_status") or "") != "succeeded":
        raise LookupError("knowledge_document_not_ready")
    return document


async def read_knowledge_document(
    *, tenant_id: str, user_id: str, scope: str, source_id: str,
    offset: int = 0, char_offset: int = 0, max_chars: int = 5000,
    expected_document_id: str = "", expected_checksum: str = "",
) -> dict[str, Any]:
    if not source_id.strip():
        raise ValueError("knowledge_source_id_required")
    if offset < 0 or char_offset < 0:
        raise ValueError("knowledge_cursor_invalid")
    tenant_id = resolve_main_id(tenant_id)
    max_chars = max(1000, min(max_chars, 5000))
    document = await _resolve_document(
        tenant_id=tenant_id, user_id=user_id, scope=scope, source_id=source_id, require_parsed=False,
    )
    document_id = str(document["_id"])
    if (expected_document_id and document_id != expected_document_id) or (expected_checksum and str(document.get('checksum') or '') != expected_checksum):
        raise LookupError('knowledge_reference_changed')
    if str(document.get("parse_status") or "") != "succeeded":
        from app.knowledge_references.original_reader import read_original
        return await read_original(document, scope=scope, source_id=source_id, offset=offset, char_offset=char_offset, max_chars=max_chars)
    db = get_db()
    base = {"main_id": tenant_id, "document_id": document_id}
    stage = "raw" if await db.knowledge_document_chunks.count_documents({**base, "chunk_stage": "raw"}) else "rag"
    query = {**base, "chunk_stage": "raw"} if stage == "raw" else {
        **base, "$or": [{"chunk_stage": "rag"}, {"chunk_stage": {"$exists": False}}],
    }
    total = await db.knowledge_document_chunks.count_documents(query)
    if total == 0:
        from app.knowledge_references.original_reader import read_original
        return await read_original(document, scope=scope, source_id=source_id, offset=offset, char_offset=char_offset, max_chars=max_chars)
    if offset >= total:
        raise ValueError("knowledge_cursor_out_of_range")

    cursor = db.knowledge_document_chunks.find(query).sort([("ordinal", 1), ("_id", 1)]).skip(offset).limit(20)
    segments: list[dict[str, Any]] = []
    position, within, remaining = offset, char_offset, max_chars
    async for chunk in cursor:
        full_text = str(chunk.get("text") or "")
        if within > len(full_text):
            raise ValueError("knowledge_cursor_out_of_range")
        part = full_text[within:within + remaining]
        if part:
            segments.append({
                "chunk_id": str(chunk.get("chunk_id") or ""),
                "ordinal": int(chunk.get("ordinal") or position),
                "page_no": chunk.get("page_no"),
                "title_path": [str(item) for item in list(chunk.get("title_path") or [])],
                "char_offset": within,
                "text": part,
            })
            remaining -= len(part)
        if within + len(part) < len(full_text):
            within += len(part)
            break
        position += 1
        within = 0
        if remaining == 0:
            break
    has_more = position < total
    return {
        "success": True,
        "scope": scope,
        "source_id": source_id,
        "document_id": document_id,
        "document_name": str(document.get("name") or document.get("original_filename") or ""),
        "checksum": str(document.get("checksum") or ""),
        "chunk_stage": stage,
        "total_chunks": total,
        "segments": segments,
        "has_more": has_more,
        "next_cursor": {"offset": position, "char_offset": within} if has_more else None,
    }
