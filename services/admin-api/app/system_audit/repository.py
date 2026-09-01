from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from app.core.db import get_db
from .constants import SYSTEM_AUDIT_COLLECTION


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SystemAuditRepository:
    def __init__(self, db: Any | None = None) -> None:
        self.db = db or get_db()

    async def ensure_indexes(self) -> None:
        collection = self.db[SYSTEM_AUDIT_COLLECTION]
        await collection.create_index([("main_id", 1), ("occurred_at", -1)], name="system_audit_main_time")
        await collection.create_index([("main_id", 1), ("module", 1), ("occurred_at", -1)], name="system_audit_main_module_time")
        await collection.create_index([("main_id", 1), ("result", 1), ("occurred_at", -1)], name="system_audit_main_result_time")

    async def record_management_operation(self, document: dict[str, Any]) -> None:
        await self.db[SYSTEM_AUDIT_COLLECTION].insert_one({
            "_id": uuid.uuid4().hex,
            "occurred_at": utcnow(),
            **document,
        })
