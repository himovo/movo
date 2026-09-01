"""Minimal Conversation projection independent from the legacy Agent runtime."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError


class ConversationRepository:
    def __init__(self, db: Any) -> None:
        self._sessions = db.chat_sessions
        self._messages = db.chat_messages

    async def ensure_indexes(self) -> None:
        await self._messages.create_index(
            "message_id",
            unique=True,
            partialFilterExpression={"message_id": {"$type": "string"}},
            name="unique_string_message_id",
        )
        await self._messages.create_index(
            [("main_id", 1), ("user_id", 1), ("session_id", 1), ("seq", 1)],
        )

    async def create(self, *, tenant_id: str, user_id: str, title: str) -> dict[str, Any]:
        now = datetime.utcnow()
        document = {
            "user_id": user_id,
            "main_id": tenant_id,
            "title": (title.strip() or "New Chat")[:160],
            "created_at": now,
            "updated_at": now,
            "last_message_at": None,
            "last_message_preview": None,
            "message_count": 0,
            "next_message_seq": 0,
            "runtime_owner": "dsh",
        }
        result = await self._sessions.insert_one(document)
        document["_id"] = result.inserted_id
        return document

    async def delete_if_empty(self, conversation_id: str, *, tenant_id: str, user_id: str) -> None:
        if not ObjectId.is_valid(conversation_id):
            return
        await self._sessions.delete_one(
            {
                "_id": ObjectId(conversation_id),
                "main_id": tenant_id,
                "user_id": user_id,
                "message_count": 0,
            }
        )

    async def owned(self, conversation_id: str, *, tenant_id: str, user_id: str) -> dict[str, Any]:
        if not ObjectId.is_valid(conversation_id):
            raise LookupError("conversation_not_found")
        row = await self._sessions.find_one(
            {"_id": ObjectId(conversation_id), "main_id": tenant_id, "user_id": user_id}
        )
        if row is None:
            raise LookupError("conversation_not_found")
        return row

    async def message(self, message_id: str, *, tenant_id: str, user_id: str) -> dict[str, Any] | None:
        return await self._messages.find_one(
            {"message_id": message_id, "main_id": tenant_id, "user_id": user_id}
        )

    async def append_message(
        self,
        *,
        conversation_id: str,
        tenant_id: str,
        user_id: str,
        role: str,
        content: str,
        message_id: str,
        images: list[dict[str, Any]] | None = None,
        documents: list[dict[str, Any]] | None = None,
        execution_events: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        existing = await self._messages.find_one({"message_id": message_id})
        if existing is not None:
            if (
                str(existing.get("main_id")) != tenant_id
                or str(existing.get("user_id")) != user_id
                or str(existing.get("session_id")) != conversation_id
            ):
                raise ValueError("message id belongs to another Conversation")
            return existing
        session = await self._sessions.find_one_and_update(
            {"_id": ObjectId(conversation_id), "main_id": tenant_id, "user_id": user_id},
            {"$inc": {"next_message_seq": 1}},
            return_document=ReturnDocument.AFTER,
        )
        if session is None:
            raise LookupError("conversation_not_found")
        now = datetime.utcnow()
        document = {
            "session_id": session["_id"],
            "user_id": user_id,
            "main_id": tenant_id,
            "seq": int(session.get("next_message_seq") or 1),
            "role": role,
            "content": content,
            "images": list(images or []),
            "documents": list(documents or []),
            "message_id": message_id,
            "execution_events": list(execution_events or []),
            "created_at": now,
            "runtime_owner": "dsh",
        }
        try:
            await self._messages.insert_one(document)
        except DuplicateKeyError:
            existing = await self._messages.find_one({"message_id": message_id})
            if existing is not None:
                return existing
            raise
        await self._sessions.update_one(
            {"_id": session["_id"], "main_id": tenant_id, "user_id": user_id},
            {
                "$set": {
                    "updated_at": now,
                    "last_message_at": now,
                    "last_message_preview": content[:200],
                },
                "$inc": {"message_count": 1},
            },
        )
        return document

    async def update_assistant_projection(
        self,
        *,
        message_id: str,
        tenant_id: str,
        user_id: str,
        content: str,
        execution_events: list[dict[str, Any]],
        evidence_bundles: list[dict[str, Any]] | None = None,
    ) -> None:
        update = {"content": content, "execution_events": execution_events}
        if evidence_bundles is not None:
            update["evidence_bundles"] = list(evidence_bundles)
        result = await self._messages.update_one(
            {"message_id": message_id, "main_id": tenant_id, "user_id": user_id},
            {"$set": update},
        )
        if result.matched_count == 0:
            raise LookupError("assistant_message_not_found")

    async def mark_active_run(
        self,
        *,
        conversation_id: str,
        tenant_id: str,
        user_id: str,
        message_id: str,
        run_id: str,
    ) -> None:
        result = await self._sessions.update_one(
            {"_id": ObjectId(conversation_id), "main_id": tenant_id, "user_id": user_id},
            {"$set": {
                "active_run": {
                    "run_id": run_id,
                    "message_id": message_id,
                    "source": "dsh",
                    "status": "running",
                    "started_at": datetime.utcnow(),
                },
                "updated_at": datetime.utcnow(),
            }},
        )
        if result.matched_count == 0:
            raise LookupError("conversation_not_found")

    async def clear_active_run(
        self,
        *,
        conversation_id: str,
        tenant_id: str,
        user_id: str,
        message_id: str,
    ) -> None:
        if not ObjectId.is_valid(conversation_id):
            return
        await self._sessions.update_one(
            {
                "_id": ObjectId(conversation_id),
                "main_id": tenant_id,
                "user_id": user_id,
                "active_run.message_id": message_id,
            },
            {"$unset": {"active_run": ""}, "$set": {"updated_at": datetime.utcnow()}},
        )

    async def set_pending_approval_count(
        self, *, conversation_id: str, tenant_id: str, user_id: str, count: int,
    ) -> None:
        if not ObjectId.is_valid(conversation_id):
            return
        await self._sessions.update_one(
            {"_id": ObjectId(conversation_id), "main_id": tenant_id, "user_id": user_id},
            {"$set": {"pending_approval_count": max(0, int(count)), "updated_at": datetime.utcnow()}},
        )

    async def suspend_active_run(
        self,
        *,
        conversation_id: str,
        tenant_id: str,
        user_id: str,
        message_id: str,
        intervention: dict[str, Any],
    ) -> None:
        if not ObjectId.is_valid(conversation_id):
            return
        await self._sessions.update_one(
            {
                "_id": ObjectId(conversation_id),
                "main_id": tenant_id,
                "user_id": user_id,
                "active_run.message_id": message_id,
            },
            {"$set": {
                "active_run.status": "suspended",
                "active_run.suspension_id": str(intervention.get("suspension_id") or ""),
                "active_run.node_id": str(intervention.get("node_id") or ""),
                "active_run.reason": str(intervention.get("reason") or ""),
                "updated_at": datetime.utcnow(),
            }},
        )
