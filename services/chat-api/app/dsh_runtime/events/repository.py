"""Idempotent Kernel Event inbox and UI projection journal."""

from __future__ import annotations

import asyncio
from datetime import datetime
from dataclasses import dataclass
from typing import Any, Mapping

from pymongo import ReturnDocument, UpdateOne

from app.dsh_runtime.contracts import KernelEventEnvelope

from .projection import KernelEventProjector

# The durable per-message ordinal counter lives on the chat_messages row
# (T3 normalization): every durable projection row for a message draws its
# ascending, distinct stream_seq from this one counter.
MESSAGE_STREAM_COUNTER = "next_stream_seq"


class StreamSequenceReservationError(RuntimeError):
    """The durable per-message stream ordinal could not be reserved.

    Raised LOUDLY (never swallowed) when the ``chat_messages`` row for the
    message is missing: ``find_one_and_update`` returns ``None`` and an
    ``upsert`` would silently fabricate a bogus message row instead. The
    failure is allowed to propagate so it poisons the caller's writer for
    the whole message rather than dropping one batch.
    """

    code = "stream_sequence_reservation_failed"

    def __init__(self, *, message_id: str, span: int) -> None:
        self.message_id = message_id
        self.span = span
        super().__init__(
            f"cannot reserve {span} durable stream ordinals for message"
            f" {message_id}: no chat_messages row exists"
        )


@dataclass(frozen=True)
class KernelEventWrite:
    event: KernelEventEnvelope
    projected: dict[str, Any] | None


class KernelEventRepository:
    INBOX = "kernel_event_inbox"
    PROJECTIONS = "kernel_event_projections"
    MESSAGES = "chat_messages"

    def __init__(self, db: Any, projector: KernelEventProjector | None = None) -> None:
        self._inbox = db[self.INBOX]
        self._projections = db[self.PROJECTIONS]
        self._messages = db[self.MESSAGES]
        self._projector = projector or KernelEventProjector()

    async def ensure_indexes(self) -> None:
        await self._inbox.create_index([("kernel_session_id", 1), ("cursor", 1)], unique=True)
        await self._inbox.create_index("event_id", unique=True)
        await self._projections.create_index("event_id", unique=True)
        await self._projections.create_index(
            [("tenant_id", 1), ("user_id", 1), ("message_id", 1), ("stream_seq", 1)]
        )
        # T3: the durable execution-replay query filters tenant_id + message_id
        # and ranges stream_seq, leaving user_id unconstrained — the
        # pre-existing four-field index above cannot serve it.
        await self._projections.create_index(
            [("tenant_id", 1), ("message_id", 1), ("stream_seq", 1)],
            name="durable_projection_message_stream",
        )

    async def ingest(
        self,
        event: KernelEventEnvelope,
        *,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        message_id: str,
    ) -> dict[str, Any] | None:
        projected = self.project(event, message_id=message_id)
        await self.persist_batch(
            [KernelEventWrite(event=event, projected=projected)],
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            message_id=message_id,
        )
        return projected

    def project(
        self,
        event: KernelEventEnvelope,
        *,
        message_id: str,
        tool_presentations: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        return self._projector.project(
            event,
            message_id=message_id,
            tool_presentations=tool_presentations,
        )

    async def reserve_stream_ordinals(self, *, message_id: str, span: int) -> list[int]:
        """Reserve `span` contiguous, ascending durable ordinals for a message.

        One atomic ``$inc`` on the message row is the serialization point, so
        concurrent reservers can never overlap; a partly-consumed block is
        abandoned rather than reused, which makes the durable ordinal stream
        strictly ascending and distinct but NOT contiguous.
        """
        size = max(1, int(span))
        row = await self._messages.find_one_and_update(
            {"message_id": message_id},
            {"$inc": {MESSAGE_STREAM_COUNTER: size}},
            return_document=ReturnDocument.AFTER,
        )
        if row is None:
            raise StreamSequenceReservationError(message_id=message_id, span=size)
        end = int(row.get(MESSAGE_STREAM_COUNTER) or size)
        return list(range(end - size + 1, end + 1))

    async def persist_batch(
        self,
        writes: list[KernelEventWrite],
        *,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        message_id: str,
    ) -> None:
        if not writes:
            return
        now = datetime.utcnow()
        ordinals = await self._reserve_for(writes, message_id=message_id)
        ordinal_index = 0
        inbox_ops: list[UpdateOne] = []
        projection_ops: list[UpdateOne] = []
        for write in writes:
            event = write.event
            inbox = {
                "event_id": event.event_id,
                "kernel_session_id": event.session_id,
                "runtime_id": event.runtime_id,
                "profile_version": event.profile_version,
                "cursor": event.cursor,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "conversation_id": conversation_id,
                "message_id": message_id,
                "kernel_event": event.model_dump(mode="json"),
                "received_at": now,
            }
            inbox_ops.append(UpdateOne({"event_id": event.event_id}, {"$setOnInsert": inbox}, upsert=True))
            if write.projected is not None:
                row = {
                    **write.projected,
                    "stream_seq": ordinals[ordinal_index],
                    "stream_seq_end": ordinals[ordinal_index],
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                    "kernel_session_id": event.session_id,
                    "created_at": now,
                }
                ordinal_index += 1
                projection_ops.append(
                    UpdateOne({"event_id": row["event_id"]}, {"$setOnInsert": row}, upsert=True)
                )
        operations = [self._inbox.bulk_write(inbox_ops, ordered=True)]
        if projection_ops:
            operations.append(self._projections.bulk_write(projection_ops, ordered=True))
        await asyncio.gather(*operations)

    async def persist_projections(
        self,
        rows: list[dict[str, Any]],
        *,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        message_id: str,
        kernel_session_id: str,
    ) -> None:
        """Persist ASKAI-owned side-band V3 rows without forging kernel events."""

        if not rows:
            return
        now = datetime.utcnow()
        ordinals = await self.reserve_stream_ordinals(
            message_id=message_id, span=max(1, len(rows))
        )
        operations: list[UpdateOne] = []
        for projected, seq in zip(rows, ordinals):
            row = {
                **dict(projected),
                "stream_seq": seq,
                "stream_seq_end": seq,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "conversation_id": conversation_id,
                "message_id": message_id,
                "kernel_session_id": kernel_session_id,
                "created_at": now,
            }
            operations.append(
                UpdateOne({"event_id": row["event_id"]}, {"$setOnInsert": row}, upsert=True)
            )
        await self._projections.bulk_write(operations, ordered=True)

    async def _reserve_for(
        self, writes: list[KernelEventWrite], *, message_id: str
    ) -> list[int]:
        if not any(write.projected is not None for write in writes):
            return []
        return await self.reserve_stream_ordinals(
            message_id=message_id, span=max(1, len(writes))
        )

    async def list_for_message(
        self,
        message_id: str,
        *,
        tenant_id: str,
        user_id: str,
        after_cursor: int = 0,
    ) -> list[dict[str, Any]]:
        # Conversation-scoped: events are attributed to the run's author at
        # write time, but every member of the conversation may read them
        # (session-sharing plan todo 7). user_id stays in the signature for
        # call-shape compatibility with the runtime callers (turn_recovery).
        result: list[dict[str, Any]] = []
        cursor = self._projections.find(
            {
                "message_id": message_id,
                "tenant_id": tenant_id,
                "stream_seq": {"$gt": max(0, int(after_cursor))},
            },
            {"_id": 0, "tenant_id": 0, "user_id": 0, "conversation_id": 0, "message_id": 0, "kernel_session_id": 0, "created_at": 0},
        ).sort("stream_seq", 1)
        async for row in cursor:
            result.append(row)
        return result

    async def all_for_message(self, message_id: str, *, tenant_id: str, user_id: str) -> list[dict[str, Any]]:
        return await self.list_for_message(message_id, tenant_id=tenant_id, user_id=user_id, after_cursor=0)
