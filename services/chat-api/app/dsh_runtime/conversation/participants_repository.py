"""Non-owner participant memberships for shared conversations.

Rows in ``session_participants``: one per (conversation, user), soft-removed
on leave and reactivated on re-join. Owner membership lives on the session
document, not here; every method is scoped by tenant (``main_id``) and never
filters by a viewer identity beyond that. The unique index omits
``main_id`` because ``conversation_id`` is the session ``_id`` (ObjectId),
which is globally unique across tenants.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pymongo import DESCENDING
from pymongo.errors import DuplicateKeyError


class SessionParticipantsRepository:
    def __init__(self, db: Any) -> None:
        self._collection = db.session_participants

    async def ensure_indexes(self) -> None:
        await self._collection.create_index(
            [("conversation_id", 1), ("user_id", 1)],
            unique=True,
            name="unique_conversation_participant",
        )
        await self._collection.create_index(
            [("main_id", 1), ("user_id", 1), ("joined_at", DESCENDING)],
            name="participant_memberships_by_user",
        )

    async def add(self, *, tenant_id: str, conversation_id: str, user_id: str) -> None:
        """Idempotently join ``user_id`` to ``conversation_id``.

        An upsert so a re-join reuses the row and clears ``removed_at``.
        Concurrent upserts race the unique index; per MongoDB's documented
        remedy the loser retries the update, which then matches the winner's
        row.
        """
        filter = {
            "main_id": tenant_id,
            "conversation_id": conversation_id,
            "user_id": user_id,
        }
        update = {
            "$set": {
                "role": "participant",
                "joined_at": datetime.utcnow(),
                "removed_at": None,
                "last_read_seq": 0,
            }
        }
        try:
            await self._collection.update_one(filter, update, upsert=True)
        except DuplicateKeyError:
            await self._collection.update_one(filter, update, upsert=True)

    async def remove(self, conversation_id: str, *, tenant_id: str, user_id: str) -> None:
        await self._collection.update_one(
            {
                "main_id": tenant_id,
                "conversation_id": conversation_id,
                "user_id": user_id,
            },
            {"$set": {"removed_at": datetime.utcnow()}},
        )

    async def list(
        self,
        conversation_id: str,
        *,
        tenant_id: str,
        include_removed: bool = False,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {
            "main_id": tenant_id,
            "conversation_id": conversation_id,
        }
        if not include_removed:
            query["removed_at"] = None
        cursor = self._collection.find(query).sort("joined_at", 1)
        return [row async for row in cursor]

    async def is_member(self, conversation_id: str, *, tenant_id: str, user_id: str) -> bool:
        row = await self._collection.find_one(
            {
                "main_id": tenant_id,
                "conversation_id": conversation_id,
                "user_id": user_id,
                "removed_at": None,
            },
            projection={"_id": 1},
        )
        return row is not None

    async def list_for_user(
        self,
        tenant_id: str,
        *,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        cursor = (
            self._collection.find(
                {
                    "main_id": tenant_id,
                    "user_id": user_id,
                    "removed_at": None,
                }
            )
            .sort("joined_at", DESCENDING)
            .skip(max(0, int(offset)))
            .limit(max(1, int(limit)))
        )
        return [row async for row in cursor]

    async def set_read_cursor(
        self,
        conversation_id: str,
        *,
        tenant_id: str,
        user_id: str,
        last_read_seq: int,
    ) -> None:
        await self._collection.update_one(
            {
                "main_id": tenant_id,
                "conversation_id": conversation_id,
                "user_id": user_id,
            },
            {"$set": {"last_read_seq": int(last_read_seq)}},
        )

    async def delete_for_conversation(self, conversation_id: str, *, tenant_id: str) -> None:
        await self._collection.delete_many(
            {
                "main_id": tenant_id,
                "conversation_id": conversation_id,
            }
        )
