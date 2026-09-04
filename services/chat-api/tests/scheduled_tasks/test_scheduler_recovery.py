import asyncio
from datetime import datetime

from app.scheduled_tasks import scheduler as scheduler_module


class FakeRepository:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.pending = [{"run_id": "run-1", "job_id": "job-1", "scheduled_for": datetime(2026, 9, 5, 1)}]

    async def claim_pending_run(self, **_kwargs):
        return self.pending.pop(0) if self.pending else None

    async def get_job_for_run(self, _run):
        return {"_id": "job-1", "run_at": datetime(2026, 9, 5, 9), "timezone": "Asia/Shanghai"}

    async def release_after_dispatch(self, _job, *, scheduled_for):
        assert scheduled_for == datetime(2026, 9, 5, 1)
        self.events.append("released")


class FakeRunner:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def start(self, _job, _run):
        self.events.append("started")


def test_pending_run_is_started_before_schedule_advances(monkeypatch) -> None:
    repository = FakeRepository()
    monkeypatch.setattr(scheduler_module, "scheduled_task_repository", repository)
    monkeypatch.setattr(scheduler_module, "scheduled_chat_runner", FakeRunner(repository.events))

    asyncio.run(scheduler_module.ScheduledTaskScheduler()._recover_pending())

    assert repository.events == ["started", "released"]
