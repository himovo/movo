from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, Optional

from pymongo import ReturnDocument

from app.core.db import get_db

from .contracts import SuspensionRecord, SuspensionStatus


class SuspensionStore:
    def __init__(self) -> None:
        self._collection = "runtime_suspensions"

    async def ensure_indexes(self) -> None:
        collection = get_db()[self._collection]
        await collection.create_index("suspension_id", unique=True)
        await collection.create_index([
            ("user_id", 1), ("task_id", 1), ("suspension_type", 1),
            ("status", 1), ("updated_at", -1),
        ])
        await collection.create_index([
            ("user_id", 1), ("run_id", 1), ("node_id", 1),
            ("status", 1), ("updated_at", -1),
        ])

    async def create(self, record: SuspensionRecord) -> SuspensionRecord:
        now = datetime.utcnow()
        record.updated_at = now
        await get_db()[self._collection].update_one(
            {"suspension_id": record.suspension_id},
            {"$setOnInsert": record.model_dump(mode="json")},
            upsert=True,
        )
        stored = await self.get(record.suspension_id)
        return stored or record

    async def get(self, suspension_id: str) -> Optional[SuspensionRecord]:
        row = await get_db()[self._collection].find_one({"suspension_id": suspension_id})
        return self._model(row)

    async def latest_active(
        self,
        *,
        user_id: str,
        task_id: str,
        suspension_type: str = "",
    ) -> Optional[SuspensionRecord]:
        query: Dict[str, Any] = {
            "user_id": user_id,
            "task_id": task_id,
            "status": {"$in": [SuspensionStatus.SUSPENDED.value, SuspensionStatus.READY.value]},
        }
        if suspension_type:
            query["suspension_type"] = suspension_type
        row = await get_db()[self._collection].find_one(query, sort=[("updated_at", -1)])
        return self._model(row)

    async def latest_active_for_node(
        self,
        *,
        user_id: str,
        run_id: str,
        node_id: str,
        suspension_type: str = "",
    ) -> Optional[SuspensionRecord]:
        query: Dict[str, Any] = {
            "user_id": user_id,
            "run_id": run_id,
            "node_id": node_id,
            "status": {"$in": [SuspensionStatus.SUSPENDED.value, SuspensionStatus.READY.value]},
        }
        if suspension_type:
            query["suspension_type"] = suspension_type
        row = await get_db()[self._collection].find_one(query, sort=[("updated_at", -1)])
        return self._model(row)

    async def latest_active_for_run(self, *, user_id: str, run_id: str) -> Optional[SuspensionRecord]:
        row = await get_db()[self._collection].find_one(
            {
                "user_id": user_id,
                "run_id": run_id,
                "status": {"$in": [SuspensionStatus.SUSPENDED.value, SuspensionStatus.READY.value]},
            },
            sort=[("updated_at", -1)],
        )
        return self._model(row)

    async def transition(
        self,
        *,
        suspension_id: str,
        user_id: str,
        from_statuses: Iterable[SuspensionStatus | str],
        to_status: SuspensionStatus,
        updates: Optional[Dict[str, Any]] = None,
    ) -> Optional[SuspensionRecord]:
        allowed = [item.value if isinstance(item, SuspensionStatus) else str(item) for item in from_statuses]
        now = datetime.utcnow()
        payload: Dict[str, Any] = {"status": to_status.value, "updated_at": now}
        payload.update(dict(updates or {}))
        if to_status == SuspensionStatus.READY:
            payload.setdefault("ready_at", now)
        elif to_status == SuspensionStatus.RESUMED:
            payload.setdefault("resumed_at", now)
        row = await get_db()[self._collection].find_one_and_update(
            {
                "suspension_id": suspension_id,
                "user_id": user_id,
                "status": {"$in": allowed},
            },
            {"$set": payload},
            return_document=ReturnDocument.AFTER,
        )
        return self._model(row)

    @staticmethod
    def _model(row: Any) -> Optional[SuspensionRecord]:
        if not isinstance(row, dict):
            return None
        data = dict(row)
        data.pop("_id", None)
        return SuspensionRecord.model_validate(data)
