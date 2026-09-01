"""Durable ASKAI-owned final content, kept outside the DSH model context."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.db import get_db


class AuthoritativeDeliveryRepository:
    COLLECTION = "enterprise_authoritative_deliveries"

    async def ensure_indexes(self) -> None:
        collection = get_db()[self.COLLECTION]
        await collection.create_index("action_id", unique=True)
        await collection.create_index(
            [("tenant_id", 1), ("user_id", 1), ("message_id", 1), ("created_at", 1)]
        )
        await collection.create_index(
            [("tenant_id", 1), ("user_id", 1), ("message_id", 1), ("tool_name", 1), ("accepted", 1)]
        )

    async def save(
        self,
        *,
        action_id: str,
        tenant_id: str,
        user_id: str,
        message_id: str,
        tool_name: str,
        markdown: str,
        accepted: bool = True,
        acceptance: dict[str, Any] | None = None,
        source_action_id: str = "",
    ) -> None:
        content = str(markdown or "").strip()
        if not action_id or not message_id or not content or not accepted:
            return
        await get_db()[self.COLLECTION].update_one(
            {"action_id": action_id},
            {"$setOnInsert": {
                "action_id": action_id,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "message_id": message_id,
                "tool_name": tool_name,
                "accepted": True,
                "acceptance": dict(acceptance or {}),
                "content_type": "text/markdown",
                "content": content,
                "source_action_id": str(source_action_id or ""),
                "created_at": datetime.utcnow(),
            }},
            upsert=True,
        )

    async def get(
        self,
        action_id: str,
        *,
        tenant_id: str,
        user_id: str,
        message_id: str,
    ) -> dict[str, Any] | None:
        if not action_id:
            return None
        return await get_db()[self.COLLECTION].find_one(
            {
                "action_id": action_id,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "message_id": message_id,
            },
            {"_id": 0},
        )

    async def find_accepted(
        self,
        *,
        tenant_id: str,
        user_id: str,
        message_id: str,
        tool_name: str,
    ) -> dict[str, Any] | None:
        if not message_id or not tool_name:
            return None
        return await get_db()[self.COLLECTION].find_one(
            {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "message_id": message_id,
                "tool_name": tool_name,
                "accepted": True,
            },
            {"_id": 0},
            sort=[("created_at", -1)],
        )


__all__ = ["AuthoritativeDeliveryRepository"]
