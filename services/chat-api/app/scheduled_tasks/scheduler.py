from __future__ import annotations

import asyncio
import logging
import uuid

from .repository import scheduled_task_repository
from .runner import scheduled_chat_runner
from .dsh_execution import scheduled_dsh_execution
from .schedule import utc_now
from .migration import migrate_legacy_schedules


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
        await migrate_legacy_schedules()
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
            asyncio.create_task(self._claim_and_execute(job, run), name=f"scheduled-run-{run['run_id']}")
        return run

    async def _claim_and_execute(self, job: dict, run: dict) -> None:
        claimed = await scheduled_task_repository.claim_pending_run(
            worker_id=self.worker_id, run_id=str(run.get("run_id") or "")
        )
        if claimed:
            await self._execute_claimed(job, claimed)

    async def _execute_claimed(self, job: dict, run: dict) -> None:
        await scheduled_chat_runner.start(job, run)
        if not bool(run.get("manual")):
            await scheduled_task_repository.release_after_dispatch(
                job, scheduled_for=run.get("scheduled_for") or utc_now()
            )

    async def _recover_pending(self) -> None:
        for _ in range(20):
            run = await scheduled_task_repository.claim_pending_run(worker_id=self.worker_id)
            if not run:
                return
            job = await scheduled_task_repository.get_job_for_run(run)
            if not job:
                logger.error(
                    "scheduled run has no job",
                    extra={"event": "scheduled.orphaned_run", "run_id": run.get("run_id")},
                )
                await scheduled_task_repository.fail_pending_run(run, "定时任务已被删除，无法恢复执行")
                continue
            await self._execute_claimed(job, run)

    async def _loop(self) -> None:
        while not self._stopping.is_set():
            try:
                await self._recover_pending()
                for _ in range(20):
                    job = await scheduled_task_repository.claim_due_job(worker_id=self.worker_id)
                    if not job:
                        break
                    scheduled_for = job.get("next_run_at") or utc_now()
                    run = await scheduled_task_repository.create_run(job, scheduled_for=scheduled_for)
                    if run:
                        await self._claim_and_execute(job, run)
                    else:
                        existing = await scheduled_task_repository.get_run(job, scheduled_for=scheduled_for)
                        if existing and str(existing.get("status") or "") in {"queued", "dispatching"}:
                            await self._claim_and_execute(job, existing)
                        else:
                            await scheduled_task_repository.release_after_dispatch(job, scheduled_for=scheduled_for)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("scheduled dispatcher iteration failed", extra={"event": "scheduled.dispatch_failed"})
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass


scheduled_task_scheduler = ScheduledTaskScheduler()
