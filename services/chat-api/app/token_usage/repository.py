from __future__ import annotations

from datetime import datetime
from typing import Any

from app.token_usage.models import TokenUsageRecord


class TokenUsageRepository:
    def __init__(self, db: Any) -> None:
        self._coll = db.token_usage_logs

    async def insert(self, record: TokenUsageRecord) -> None:
        await self._coll.insert_one(record.model_dump())

    async def mark_push_result(self, request_id: str, *, status: str, error: str = "") -> None:
        await self._coll.update_one(
            {"request_id": str(request_id or "")},
            {
                "$set": {
                    "push_status": str(status or ""),
                    "push_error": str(error or ""),
                    "updated_at": datetime.utcnow(),
                }
            },
        )
