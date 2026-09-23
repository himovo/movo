"""Minimal Conversation projection independent from the legacy Agent runtime."""

# allow: SIZE_OK — the plan pins this single file as the todo-6 seam; todos
# 13/14/19 address this module by line number, so a split is a later todo's
# decision, not T06's.

from __future__ import annotations

from datetime import datetime
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError, OperationFailure

UNIQUE_MESSAGE_SEQ_INDEX_NAME = "unique_main_session_seq"


class MessageSequenceIndexConflict(RuntimeError):
    """Pre-existing chat_messages rows duplicate (main_id, session_id, seq).

    Startup must abort: the unique per-session sequence index cannot be built
    over duplicate data, and silently skipping the index or de-duplicating
    automatically would corrupt the sequence contract.
    """

    def __init__(self, index_name: str, samples: list[dict[str, Any]]) -> None:
        self.index_name = index_name
        self.samples = samples
        super().__init__(
            f"cannot create unique index {index_name!r} on chat_messages:"
            " pre-existing rows duplicate (main_id, session_id, seq);"
            f" sample offending rows: {samples}; aborting startup - run the"
            " one-time re-sequence pass from the operator runbook"
            " (session-sharing plan todo 33) and restart"
        )


class MessageSequenceConflict(RuntimeError):
    """An append raced another writer for the same per-session sequence slot.

    Retryable: the next attempt re-seeds the counter via the $max floor and
    mints a fresh seq. Carries a stable ``code`` so the endpoint layer can map
    it to a retryable status instead of an unmapped 500 (session-sharing plan
    todo 10).
    """

    code = "message_sequence_conflict"

    def __init__(self, *, conversation_id: str, seq: int) -> None:
        self.conversation_id = conversation_id
        self.seq = seq
        super().__init__(
            f"message seq {seq} was already taken by a concurrent writer in"
            f" conversation {conversation_id}; retry the append"
        )


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
        await self._sessions.create_index(
            [("main_id", 1), ("share_token_hash", 1)],
            unique=True,
            partialFilterExpression={"share_token_hash": {"$type": "string"}},
            name="unique_main_share_token_hash",
        )
        try:
            await self._messages.create_index(
                [("main_id", 1), ("session_id", 1), ("seq", 1)],
                unique=True,
                name=UNIQUE_MESSAGE_SEQ_INDEX_NAME,
            )
        except OperationFailure:
            # The failed build's server error carries no usable samples: find the
            # offending rows via aggregation, and re-raise when the failure is
            # not caused by duplicates.
            samples = await self._duplicate_message_seq_samples()
            if samples:
                raise MessageSequenceIndexConflict(
                    UNIQUE_MESSAGE_SEQ_INDEX_NAME, samples
                ) from None
            raise

    async def _duplicate_message_seq_samples(self) -> list[dict[str, Any]]:
        cursor = self._messages.aggregate(
            [
                {
                    "$group": {
                        "_id": {
                            "main_id": "$main_id",
                            "session_id": "$session_id",
                            "seq": "$seq",
                        },
                        "count": {"$sum": 1},
                        "message_ids": {"$firstN": {"input": "$message_id", "n": 3}},
                    }
                },
                {"$match": {"count": {"$gt": 1}}},
                {"$limit": 5},
            ]
        )
        samples: list[dict[str, Any]] = []
        async for row in cursor:
            key = row["_id"]
            samples.append(
                {
                    "main_id": str(key.get("main_id")),
                    "session_id": str(key.get("session_id")),
                    "seq": key.get("seq"),
                    "count": row["count"],
                    "message_ids": [str(message_id) for message_id in row["message_ids"]],
                }
            )
        return samples

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
            "share_token_hash": None,
            "share_expires_at": None,
            "share_revoked_at": None,
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
        # Session-scoped read: message ids are globally unique strings (the
        # unique_string_message_id index proves it), so only the tenant scopes
        # the read. user_id stays in the signature for call-shape
        # compatibility with the existing runtime callers.
        return await self._messages.find_one(
            {"message_id": message_id, "main_id": tenant_id}
        )

    async def list_messages(
        self,
        tenant_id: str,
        conversation_id: str,
        after_seq: int | None = None,
    ) -> list[dict[str, Any]]:
        if not ObjectId.is_valid(conversation_id):
            raise LookupError("conversation_not_found")
        query: dict[str, Any] = {
            "main_id": tenant_id,
            "session_id": ObjectId(conversation_id),
        }
        if after_seq is not None:
            query["seq"] = {"$gt": after_seq}
        cursor = self._messages.find(query, sort=[("seq", 1)])
        return await cursor.to_list(length=None)

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
        session_oid = ObjectId(conversation_id)
        # Session-scoped lookup: {_id, main_id} only, so a participant may
        # append. The caller layer admits members; user_id stays the message's
        # author. The counter is seeded [review-3] in the SAME atomic update:
        # the server rejects $inc and $max on the same field in one operator
        # update (ConflictingUpdateOperators, code 40), so the raise is a $set
        # whose $max expression floors the incremented counter at maxSeq + 1 -
        # a legacy writer that advanced seq without advancing next_message_seq
        # cannot cause a collision on the next DSH turn.
        max_seq_row = await self._messages.find_one(
            {"main_id": tenant_id, "session_id": session_oid},
            sort=[("seq", -1)],
        )
        max_seq = int((max_seq_row or {}).get("seq") or 0)
        session = await self._sessions.find_one_and_update(
            {"_id": session_oid, "main_id": tenant_id},
            [
                {
                    "$set": {
                        "next_message_seq": {
                            "$max": [
                                {"$add": [{"$ifNull": ["$next_message_seq", 0]}, 1]},
                                max_seq + 1,
                            ]
                        }
                    }
                }
            ],
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
            # Not the message-id idempotency case: a concurrent writer took
            # the same (main_id, session_id, seq) slot. Typed and retryable,
            # never an unmapped DuplicateKeyError (which surfaces as a 500).
            raise MessageSequenceConflict(
                conversation_id=conversation_id, seq=int(document["seq"])
            ) from None
        await self._sessions.update_one(
            {"_id": session["_id"], "main_id": tenant_id},
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
            # Session-scoped: the finalizer may call with the binding subject,
            # which can differ from the message's author.
            {"message_id": message_id, "main_id": tenant_id},
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
            # Session-scoped: a participant may start a run. The caller's
            # user_id IS the run's initiator (todo 14): recorded in the
            # active_run so cancel/approve can bind to it; a legacy row
            # without the field means "unknown" and fails closed.
            {"_id": ObjectId(conversation_id), "main_id": tenant_id},
            {"$set": {
                "active_run": {
                    "run_id": run_id,
                    "message_id": message_id,
                    "initiator_user_id": user_id,
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
            # Session-scoped: any member's finalizer may clear the claim.
            {
                "_id": ObjectId(conversation_id),
                "main_id": tenant_id,
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
            # Session-scoped: the badge must move for any caller (a rotated
            # binding or participant call must not silently no-op).
            {"_id": ObjectId(conversation_id), "main_id": tenant_id},
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
            # Session-scoped: any member's finalizer may suspend the claim.
            {
                "_id": ObjectId(conversation_id),
                "main_id": tenant_id,
                "active_run.message_id": message_id,
            },
            {"$set": {
                # Dotted-path update: the recorded initiator_user_id (todo 14)
                # and the other active_run fields are preserved, not replaced —
                # a suspended run stays attributable to its initiator.
                "active_run.status": "suspended",
                "active_run.suspension_id": str(intervention.get("suspension_id") or ""),
                "active_run.node_id": str(intervention.get("node_id") or ""),
                "active_run.reason": str(intervention.get("reason") or ""),
                "updated_at": datetime.utcnow(),
            }},
        )
