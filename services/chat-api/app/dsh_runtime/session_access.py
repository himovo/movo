"""Shared tenant-scoped read authorization for shared-session surfaces.

One owner-or-active-participant predicate, reused by the session endpoint
and the POST stream (session-sharing realtime plan, T1). The denial is
TYPED and existence-avoiding: a missing session, a cross-tenant probe, a
non-member, and a removed member are indistinguishable to the caller.
It is independent of ``CancelNotAllowedError`` (the initiator-only cancel
gate), and a share token alone never grants access — the authorizer takes
no token parameter at all, so token-bearing requests cannot be honored.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from bson import ObjectId

from app.dsh_runtime.conversation.participants_repository import (
    SessionParticipantsRepository,
)


class SessionReadUnauthenticatedError(Exception):
    """No authenticated principal was supplied (endpoint maps this to 401)."""


class SessionReadDeniedError(LookupError):
    """Existence-avoiding denial (endpoint maps this to the existing 404).

    Deliberately carries no detail: a missing session, a cross-tenant
    session id, a non-member, and a removed member all raise the same
    error, so the caller learns nothing about session existence.
    """


@dataclass(frozen=True)
class AccessLease:
    """A granted read: the viewer's identity, role, and session document."""

    session_id: str
    user_id: str
    role: str  # "owner" | "participant"
    session: Mapping[str, Any]


class SessionReadAuthorizer:
    def __init__(self, db: Any) -> None:
        self._sessions = db.chat_sessions
        self._participants = SessionParticipantsRepository(db)

    async def session_document(
        self, session_id: str, *, tenant_id: str
    ) -> Mapping[str, Any] | None:
        """Tenant-scoped session read; None for missing/invalid ids."""
        if not ObjectId.is_valid(session_id):
            return None
        return await self._sessions.find_one(
            {"_id": ObjectId(session_id), "main_id": tenant_id}
        )

    async def authorize_read(
        self,
        session_id: str,
        *,
        tenant_id: str,
        user_id: str | None,
    ) -> AccessLease:
        if not user_id:
            raise SessionReadUnauthenticatedError("authentication required")
        session_doc = await self.session_document(session_id, tenant_id=tenant_id)
        role: str | None = None
        if session_doc is not None:
            if str(session_doc.get("user_id") or "") == user_id:
                role = "owner"
            elif await self._participants.is_member(
                session_id, tenant_id=tenant_id, user_id=user_id
            ):
                role = "participant"
        if session_doc is None or role is None:
            raise SessionReadDeniedError("session_not_found")
        return AccessLease(
            session_id=session_id, user_id=user_id, role=role, session=session_doc
        )
