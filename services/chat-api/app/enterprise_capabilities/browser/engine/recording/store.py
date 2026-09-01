from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List

from app.core.db import get_db


class HumanRecordingStore:
    """Durable, de-duplicated journal for actions captured during human ownership."""

    collection_name = "browser_human_action_journal"

    def __init__(self) -> None:
        self._events: Dict[str, Dict[int, Dict[str, Any]]] = {}
        self._stopped: Dict[str, asyncio.Event] = {}
        self._index_lock = asyncio.Lock()
        self._indexes_ready = False

    async def append(self, payload: Dict[str, Any]) -> None:
        recording_id = str(payload.get("recording_id") or "").strip()
        if not recording_id:
            return
        sequence = max(0, int(payload.get("sequence") or 0))
        event = {
            **dict(payload),
            "recording_id": recording_id,
            "sequence": sequence,
            "received_at": datetime.utcnow(),
        }
        self._events.setdefault(recording_id, {})[sequence] = event
        if str(event.get("type") or "") == "recording_stopped":
            self._stopped.setdefault(recording_id, asyncio.Event()).set()
        try:
            db = get_db()
            await self._ensure_indexes(db)
            await db[self.collection_name].update_one(
                {"recording_id": recording_id, "sequence": sequence},
                {"$set": event},
                upsert=True,
            )
        except Exception:
            # The in-process journal still covers the normal suspend/resume path.
            return

    async def list(self, recording_id: str, *, user_id: str = "") -> List[Dict[str, Any]]:
        recording_id = str(recording_id or "").strip()
        if not recording_id:
            return []
        memory = [
            item for item in self._events.get(recording_id, {}).values()
            if not user_id or str(item.get("user_id") or "") == str(user_id)
        ]
        try:
            db = get_db()
            query: Dict[str, Any] = {"recording_id": recording_id}
            if user_id:
                query["user_id"] = str(user_id)
            rows = await db[self.collection_name].find(
                query, {"_id": 0},
            ).sort("sequence", 1).to_list(length=2000)
        except Exception:
            rows = []
        merged = {
            int(item.get("sequence") or 0): dict(item)
            for item in [*rows, *memory]
            if isinstance(item, dict)
        }
        return [merged[key] for key in sorted(merged)]

    async def wait_stopped(self, recording_id: str, timeout: float = 2.5, *, user_id: str = "") -> bool:
        existing = await self.list(recording_id, user_id=user_id)
        if any(str(item.get("type") or "") == "recording_stopped" for item in existing):
            return True
        event = self._stopped.setdefault(recording_id, asyncio.Event())
        try:
            await asyncio.wait_for(event.wait(), timeout=max(0.1, float(timeout)))
            return True
        except asyncio.TimeoutError:
            return False

    async def purge(self, recording_id: str, *, user_id: str = "") -> None:
        recording_id = str(recording_id or "").strip()
        if not recording_id:
            return
        self._events.pop(recording_id, None)
        self._stopped.pop(recording_id, None)
        try:
            query: Dict[str, Any] = {"recording_id": recording_id}
            if user_id:
                query["user_id"] = str(user_id)
            await get_db()[self.collection_name].delete_many(query)
        except Exception:
            return

    async def _ensure_indexes(self, db: Any) -> None:
        if self._indexes_ready:
            return
        async with self._index_lock:
            if self._indexes_ready:
                return
            collection = db[self.collection_name]
            await collection.create_index(
                [("recording_id", 1), ("sequence", 1)],
                unique=True,
                name="uq_browser_human_action",
            )
            await collection.create_index(
                [("received_at", 1)],
                expireAfterSeconds=24 * 60 * 60,
                name="ttl_browser_human_action_24h",
            )
            self._indexes_ready = True


human_recording_store = HumanRecordingStore()


__all__ = ["HumanRecordingStore", "human_recording_store"]
