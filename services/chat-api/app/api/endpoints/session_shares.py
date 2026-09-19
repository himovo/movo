"""Session-share API surface: create, join, revoke, members, leave, remove.

Status codes are pinned by the plan: 404 when the caller cannot see the
session (non-member, removed member, or cross-tenant), 403 when the caller
can see it but lacks the right, 409 when the conversation is unshareable
(no current binding or non-server execution location), 410 for expired or
revoked tokens.
"""

from __future__ import annotations

import datetime
from typing import Any, Literal

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.principal import ApiPrincipal, require_end_user_principal
from app.core.db import get_db
from app.core.tenant import add_main_scope
from app.dsh_runtime.bindings.repository import KernelBindingRepository
from app.dsh_runtime.conversation.participants_repository import SessionParticipantsRepository
from app.services.member_identity import public_display_name
from app.services.session_sharing.service import (
    SessionShareError,
    hash_token,
    is_active,
    issue_share,
    revoke_share,
)


router = APIRouter(dependencies=[Depends(require_end_user_principal)])


class CreateShareRequest(BaseModel):
    expires_in_days: int = Field(default=30, ge=1, le=365, alias="expiresInDays")


def _response(data: object = None) -> dict[str, object]:
    return {"code": 0, "message": "success", "data": data}


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _session_oid(session_id: str) -> ObjectId:
    if not ObjectId.is_valid(session_id):
        raise HTTPException(
            status_code=404,
            detail={"code": "session_not_found", "message": "Session not found"},
        )
    return ObjectId(session_id)


async def _resolve_viewer_session(
    oid: ObjectId,
    *,
    principal: ApiPrincipal,
    participants: SessionParticipantsRepository,
) -> tuple[dict[str, Any], Literal["owner", "participant"]]:
    """Return ``(session_doc, role)`` with role "owner" or "participant".

    Raises 404 when the caller cannot see the session: non-member, removed
    member, or cross-tenant. The owner branch reads the session document's
    ``user_id``; the participant branch is an active-row check (removed rows
    grant no visibility).
    """
    session_doc = await get_db().chat_sessions.find_one(add_main_scope({"_id": oid}, principal.main_id))
    role: str | None = None
    if session_doc is not None:
        if str(session_doc.get("user_id") or "") == principal.user_id:
            role = "owner"
        elif await participants.is_member(str(oid), tenant_id=principal.main_id, user_id=principal.user_id):
            role = "participant"
    if session_doc is None or role is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "session_not_found", "message": "Session not found"},
        )
    return session_doc, role


@router.post("/sessions/{session_id}/share")
async def create_session_share(
    session_id: str,
    payload: CreateShareRequest,
    principal: ApiPrincipal = Depends(require_end_user_principal),
) -> dict[str, object]:
    db = get_db()
    participants = SessionParticipantsRepository(db)
    session_doc, role = await _resolve_viewer_session(
        _session_oid(session_id), principal=principal, participants=participants,
    )
    if role != "owner":
        raise HTTPException(
            status_code=403,
            detail={"code": "session_share_owner_required", "message": "Only the session owner may share it"},
        )
    binding = await KernelBindingRepository(db).current(
        str(session_doc["_id"]), tenant_id=principal.main_id, user_id=principal.user_id,
    )
    if binding is None:
        raise HTTPException(
            status_code=409,
            detail={"code": "session_share_no_binding", "message": "This session has no current binding to share"},
        )
    if str(binding.get("execution_location") or "server") != "server":
        raise HTTPException(
            status_code=409,
            detail={"code": "session_share_not_server", "message": "Only server-run sessions can be shared"},
        )
    issued = issue_share(session_doc, now=_utcnow(), expires_in_days=payload.expires_in_days)
    await db.chat_sessions.update_one({"_id": session_doc["_id"]}, {"$set": issued["fields"]})
    active_rows = await participants.list(str(session_doc["_id"]), tenant_id=principal.main_id)
    participant_count = sum(
        1 for row in active_rows if str(row.get("user_id") or "") != principal.user_id
    )
    return _response({
        "token": issued["token"],
        "expires_at": issued["fields"]["share_expires_at"],
        "participant_count": participant_count,
    })


@router.post("/session-shares/{token}/join")
async def join_session_share(
    token: str,
    principal: ApiPrincipal = Depends(require_end_user_principal),
) -> dict[str, object]:
    db = get_db()
    try:
        token_hash = hash_token(token)
    except SessionShareError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail()) from exc
    session_doc = await db.chat_sessions.find_one(
        add_main_scope({"share_token_hash": token_hash}, principal.main_id),
    )
    if session_doc is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "session_share_not_found", "message": "Session share not found"},
        )
    if not is_active(session_doc, token, _utcnow()):
        raise HTTPException(
            status_code=410,
            detail={"code": "session_share_inactive", "message": "This session share is no longer active"},
        )
    conversation_id = str(session_doc["_id"])
    if str(session_doc.get("user_id") or "") != principal.user_id:
        # Owners are members through ownership and never get a participant row.
        await SessionParticipantsRepository(db).add(
            tenant_id=principal.main_id, conversation_id=conversation_id, user_id=principal.user_id,
        )
    return _response({"session_id": conversation_id})


@router.delete("/sessions/{session_id}/share")
async def revoke_session_share(
    session_id: str,
    principal: ApiPrincipal = Depends(require_end_user_principal),
) -> dict[str, object]:
    db = get_db()
    participants = SessionParticipantsRepository(db)
    session_doc, role = await _resolve_viewer_session(
        _session_oid(session_id), principal=principal, participants=participants,
    )
    if role != "owner":
        raise HTTPException(
            status_code=403,
            detail={"code": "session_share_owner_required", "message": "Only the session owner may revoke the share"},
        )
    await db.chat_sessions.update_one(
        {"_id": session_doc["_id"]},
        {"$set": revoke_share(now=_utcnow())},
    )
    return _response({"session_id": str(session_doc["_id"])})


@router.get("/sessions/{session_id}/participants")
async def list_participants(
    session_id: str,
    principal: ApiPrincipal = Depends(require_end_user_principal),
) -> dict[str, object]:
    participants = SessionParticipantsRepository(get_db())
    session_doc, _role = await _resolve_viewer_session(
        _session_oid(session_id), principal=principal, participants=participants,
    )
    rows = await participants.list(str(session_doc["_id"]), tenant_id=principal.main_id)
    member_ids = [str(session_doc.get("user_id") or "")]
    member_ids.extend(str(row.get("user_id") or "") for row in rows)
    candidates = [ObjectId(value) if ObjectId.is_valid(value) else value for value in member_ids if value]
    user_rows = get_db().end_users.find(
        add_main_scope({"_id": {"$in": candidates}}, principal.main_id),
        {"name": 1, "login_name": 1},
    )
    names = {
        str(row.get("_id") or ""): public_display_name(row)
        async for row in user_rows
    }
    items = [{
        "user_id": member_ids[0],
        "display_name": names.get(member_ids[0], ""),
        "role": "owner",
        "joined_at": session_doc.get("created_at"),
    }]
    items.extend({
        "user_id": str(row.get("user_id") or ""),
        "display_name": names.get(str(row.get("user_id") or ""), ""),
        "role": str(row.get("role") or "participant"),
        "joined_at": row.get("joined_at"),
    } for row in rows)
    return _response({"items": items})


@router.delete("/sessions/{session_id}/participants/me")
async def leave_session(
    session_id: str,
    principal: ApiPrincipal = Depends(require_end_user_principal),
) -> dict[str, object]:
    participants = SessionParticipantsRepository(get_db())
    session_doc, role = await _resolve_viewer_session(
        _session_oid(session_id), principal=principal, participants=participants,
    )
    if role != "participant":
        raise HTTPException(
            status_code=403,
            detail={"code": "session_share_participant_required", "message": "Only participants may leave a session"},
        )
    await participants.remove(
        str(session_doc["_id"]), tenant_id=principal.main_id, user_id=principal.user_id,
    )
    return _response({"session_id": str(session_doc["_id"])})


@router.delete("/sessions/{session_id}/participants/{user_id}")
async def remove_participant(
    session_id: str,
    user_id: str,
    principal: ApiPrincipal = Depends(require_end_user_principal),
) -> dict[str, object]:
    participants = SessionParticipantsRepository(get_db())
    session_doc, role = await _resolve_viewer_session(
        _session_oid(session_id), principal=principal, participants=participants,
    )
    if role != "owner":
        raise HTTPException(
            status_code=403,
            detail={"code": "session_share_owner_required", "message": "Only the session owner may remove participants"},
        )
    await participants.remove(
        str(session_doc["_id"]), tenant_id=principal.main_id, user_id=user_id,
    )
    return _response({"session_id": str(session_doc["_id"]), "user_id": user_id})
