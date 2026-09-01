"""Mongo-backed CRUD for execution event logs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.tenant import add_main_scope, resolve_main_id


COLLECTION_NAME = "execution_logs"


class ExecutionEventStore:
    """Version-neutral Motor event store, keyed by session and message."""

    def __init__(self, db: Any, *, collection_name: str, schema_version: int) -> None:
        self._coll = db[collection_name]
        self._schema_version = int(schema_version)

    async def append_events(
        self,
        session_id: str,
        message_id: str,
        events: List[Dict[str, Any]],
        *,
        user_id: Optional[str] = None,
        main_id: Optional[str] = None,
    ) -> None:
        if not events:
            return
        now = datetime.utcnow()
        resolved_main_id = resolve_main_id(main_id)
        query = {"session_id": session_id, "message_id": message_id}
        if resolved_main_id != "default":
            query["main_id"] = resolved_main_id
        await self._coll.update_one(
            query,
            {
                "$push": {"events": {"$each": events}},
                "$setOnInsert": {
                    "session_id": session_id,
                    "message_id": message_id,
                    "user_id": user_id,
                    "main_id": resolved_main_id,
                    "created_at": now,
                    "status": "live",
                    "schema_version": self._schema_version,
                },
                "$set": {"updated_at": now},
            },
            upsert=True,
        )

    async def get_for_message(self, message_id: str) -> Optional[Dict[str, Any]]:
        return await self._coll.find_one({"message_id": message_id})

    async def get_events_for_message(self, message_id: str) -> List[Dict[str, Any]]:
        doc = await self._coll.find_one(
            {"message_id": message_id},
            projection={"events": 1, "_id": 0},
        )
        return list((doc or {}).get("events") or [])

    async def get_events_for_session(
        self,
        session_id: str,
        *,
        main_id: Optional[str] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Return ``{message_id: [events]}`` for one session, in insertion order."""
        cursor = self._coll.find(
            add_main_scope({"session_id": session_id}, main_id),
            projection={"message_id": 1, "events": 1, "_id": 0},
        ).sort("created_at", 1)
        out: Dict[str, List[Dict[str, Any]]] = {}
        async for doc in cursor:
            mid = str(doc.get("message_id") or "")
            if mid:
                out[mid] = list(doc.get("events") or [])
        return out

    async def replace_events(
        self,
        message_id: str,
        events: List[Dict[str, Any]],
    ) -> None:
        await self._coll.update_one(
            {"message_id": message_id},
            {"$set": {"events": events, "updated_at": datetime.utcnow()}},
        )

    async def finalize(
        self,
        message_id: str,
        *,
        summary: Dict[str, Any],
        status: str = "completed",
    ) -> None:
        await self._coll.update_one(
            {"message_id": message_id},
            {
                "$set": {
                    "summary": summary,
                    "status": status,
                    "finalized_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                }
            },
        )


class LegacyExecutionLogStore(ExecutionEventStore):
    """Read-only handle for execution logs created before V3 persistence."""

    def __init__(self, db: Any, *, collection_name: str = COLLECTION_NAME, schema_version: int = 2) -> None:
        super().__init__(db, collection_name=collection_name, schema_version=schema_version)
