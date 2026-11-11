"""Retry durable sandbox cleanup independently of chat turn completion."""

from __future__ import annotations

import asyncio
import logging

from app.core.db import get_db
from .task_audit import cleanup_task_audit


logger = logging.getLogger(__name__)


async def retry_pending_task_cleanups() -> None:
    cursor = get_db().sandbox_task_audits.find(
        {"cleanup_pending": True}, {"_id": 1, "message_id": 1}
    ).limit(20)
    async for row in cursor:
        message_id = str(row.get("message_id") or "")
        if message_id:
            await cleanup_task_audit(message_id=message_id, audit_id=str(row["_id"]))


async def monitor_task_cleanups() -> None:
    while True:
        try:
            await retry_pending_task_cleanups()
        except Exception:
            logger.exception("sandbox task cleanup scan failed")
        await asyncio.sleep(60)
