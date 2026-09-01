from __future__ import annotations

import asyncio
import logging
import uuid

from .repository import scheduled_task_repository
from .runner import scheduled_chat_runner
from .dsh_execution import scheduled_dsh_execution
from .schedule import utc_now


logger = logging.getLogger(__name__)


class ScheduledTaskScheduler:
    def __init__(self) -> None:
        self.worker_id = f"scheduler-{uuid.uuid4().hex[:12]}"
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        await scheduled_task_repository.ensure_indexes()
        self._stopping.clear()
        self._task = asyncio.create_task(self._loop(), name="scheduled-task-dispatcher")

    async def stop(self) -> None:
        self._stopping.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except BaseException:
                pass
        self._task = None
        await scheduled_dsh_execution.shutdown()

    async def dispatch_now(self, job: dict) -> dict | None:
        run = await scheduled_task_repository.create_run(job, scheduled_for=utc_now(), manual=True)
        if run:
            asyncio.create_task(scheduled_chat_runner.start(job, run), name=f"scheduled-run-{run['run_id']}")
        return run

    async def _loop(self) -> None:
        while not self._stopping.is_set():
            try:
                for _ in range(20):
                    job = await scheduled_task_repository.claim_due_job(worker_id=self.worker_id)
                    if not job:
                        break
                    scheduled_for = job.get("next_run_at") or utc_now()
                    run = await scheduled_task_repository.create_run(job, scheduled_for=scheduled_for)
                    await scheduled_task_repository.release_after_dispatch(job, scheduled_for=scheduled_for)
                    if run:
                        asyncio.create_task(scheduled_chat_runner.start(job, run), name=f"scheduled-run-{run['run_id']}")
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("scheduled dispatcher iteration failed", extra={"event": "scheduled.dispatch_failed"})
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass


scheduled_task_scheduler = ScheduledTaskScheduler()
