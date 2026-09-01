from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.core.config import get_settings
from app.core.db import get_db
from app.token_usage.models import TokenUsageRecord
from app.token_usage.push import TokenUsagePushService
from app.token_usage.repository import TokenUsageRepository


logger = logging.getLogger(__name__)


class TokenUsageDispatcher:
    def __init__(self, *, queue_size: int = 512) -> None:
        self._queue_size = max(int(queue_size or 512), 16)
        self._queue: asyncio.Queue[TokenUsageRecord] | None = None
        self._worker: asyncio.Task | None = None
        self._running = False
        self._push_service = TokenUsagePushService()

    async def start(self) -> None:
        if self._running:
            return
        self._queue = asyncio.Queue(maxsize=self._queue_size)
        self._running = True
        self._worker = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._worker is not None:
            self._worker.cancel()
            try:
                await self._worker
            except BaseException:
                pass
            self._worker = None
        self._queue = None

    def submit(self, record: TokenUsageRecord) -> bool:
        queue = self._queue
        if not self._running or queue is None:
            return False
        try:
            queue.put_nowait(record)
            return True
        except asyncio.QueueFull:
            logger.warning(
                "token usage queue full",
                extra={"event": "token_usage.queue_full", "llm_request_id": record.request_id, "stage": record.stage, "model": record.model_name},
            )
            return False

    async def _run(self) -> None:
        while True:
            record = await self._queue.get()  # type: ignore[union-attr]
            try:
                repo = TokenUsageRepository(get_db())
                await repo.insert(record)
                
                # 异步累计扣减组织点数
                try:
                    from app.core.billing import deduct_points_after_request
                    await deduct_points_after_request(record.main_id, record.total_tokens)
                except Exception as b_err:
                    logger.error(f"Failed to process billing for record {record.request_id}: {b_err}")

                if get_settings().DEBUG:
                    logger.debug(
                        "token usage persisted",
                        extra={
                            "event": "token_usage.persisted",
                            "llm_request_id": record.request_id,
                            "stage": record.stage,
                            "trace_id": record.trace_id,
                            "user_id": record.user_id,
                            "total_tokens": record.total_tokens,
                        },
                    )
                push_result = await self._push_service.push(record)
                if push_result.enabled:
                    status = "success" if push_result.pushed else "failed"
                    await repo.mark_push_result(record.request_id, status=status, error=push_result.error)
            except Exception as exc:
                logger.exception(
                    "token usage persist failed",
                    extra={"event": "token_usage.persist_failed", "llm_request_id": record.request_id, "error": str(exc)},
                )
            finally:
                self._queue.task_done()  # type: ignore[union-attr]
