"""Idempotent Kernel Event inbox and UI projection journal."""

from __future__ import annotations

import asyncio
from datetime import datetime
from dataclasses import dataclass
from typing import Any, Mapping

from pymongo import UpdateOne

from app.dsh_runtime.contracts import KernelEventEnvelope

from .projection import KernelEventProjector


@dataclass(frozen=True)
class KernelEventWrite:
    event: KernelEventEnvelope
    projected: dict[str, Any] | None


class KernelEventRepository:
    INBOX = "kernel_event_inbox"
    PROJECTIONS = "kernel_event_projections"

    def __init__(self, db: Any, projector: KernelEventProjector | None = None) -> None:
        self._inbox = db[self.INBOX]
        self._projections = db[self.PROJECTIONS]
        self._projector = projector or KernelEventProjector()

    async def ensure_indexes(self) -> None:
        await self._inbox.create_index([("kernel_session_id", 1), ("cursor", 1)], unique=True)
        await self._inbox.create_index("event_id", unique=True)
        await self._projections.create_index("event_id", unique=True)
        await self._projections.create_index(
            [("tenant_id", 1), ("user_id", 1), ("message_id", 1), ("stream_seq", 1)]
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
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                    "kernel_session_id": event.session_id,
                    "created_at": now,
                }
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
        operations: list[UpdateOne] = []
        for projected in rows:
            row = {
                **dict(projected),
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

    async def list_for_message(
        self,
        message_id: str,
        *,
        tenant_id: str,
        user_id: str,
        after_cursor: int = 0,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        cursor = self._projections.find(
            {
                "message_id": message_id,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "stream_seq": {"$gt": max(0, int(after_cursor))},
            },
            {"_id": 0, "tenant_id": 0, "user_id": 0, "conversation_id": 0, "message_id": 0, "kernel_session_id": 0, "created_at": 0},
        ).sort("stream_seq", 1)
        async for row in cursor:
            result.append(row)
        return result

    async def all_for_message(self, message_id: str, *, tenant_id: str, user_id: str) -> list[dict[str, Any]]:
        return await self.list_for_message(message_id, tenant_id=tenant_id, user_id=user_id, after_cursor=0)
