from __future__ import annotations

import asyncio
from copy import deepcopy

from app.governance.suspensions.contracts import SuspensionRecord, SuspensionStatus
from app.governance.suspensions.service import SuspensionService


class MemorySuspensionStore:
    def __init__(self) -> None:
        self.rows: dict[str, SuspensionRecord] = {}

    async def create(self, record: SuspensionRecord) -> SuspensionRecord:
        self.rows.setdefault(record.suspension_id, deepcopy(record))
        return deepcopy(self.rows[record.suspension_id])

    async def get(self, suspension_id: str):
        row = self.rows.get(suspension_id)
        return deepcopy(row) if row else None

    async def transition(self, *, suspension_id, user_id, from_statuses, to_status, updates=None):
        row = self.rows.get(suspension_id)
        allowed = {item.value if isinstance(item, SuspensionStatus) else str(item) for item in from_statuses}
        if not row or row.user_id != user_id or row.status.value not in allowed:
            return None
        data = row.model_dump()
        data.update(dict(updates or {}))
        data["status"] = to_status
        self.rows[suspension_id] = SuspensionRecord.model_validate(data)
        return deepcopy(self.rows[suspension_id])


def test_only_one_resume_claim_can_consume_ready_suspension():
    asyncio.run(_only_one_resume_claim_can_consume_ready_suspension())


async def _only_one_resume_claim_can_consume_ready_suspension():
    service = SuspensionService(store=MemorySuspensionStore())
    record = await service.suspend(
        run_id="run-1",
        task_id="task-1",
        node_id="node-1",
        user_id="user-1",
        suspension_type="browser_auth",
    )
    ready = await service.mark_ready(
        suspension_id=record.suspension_id,
        user_id="user-1",
        signal={"type": "browser_auth_completed"},
    )
    assert ready and ready.status == SuspensionStatus.READY

    first = await service.claim_resume(suspension_id=record.suspension_id, user_id="user-1")
    second = await service.claim_resume(suspension_id=record.suspension_id, user_id="user-1")

    assert first and first.status == SuspensionStatus.RESUMING
    assert second is None


def test_wrong_user_cannot_mark_or_claim_suspension():
    asyncio.run(_wrong_user_cannot_mark_or_claim_suspension())


async def _wrong_user_cannot_mark_or_claim_suspension():
    service = SuspensionService(store=MemorySuspensionStore())
    record = await service.suspend(
        run_id="run-1",
        task_id="task-1",
        node_id="node-1",
        user_id="user-1",
        suspension_type="approval",
    )
    assert await service.mark_ready(
        suspension_id=record.suspension_id,
        user_id="user-2",
        signal={},
    ) is None
    assert await service.claim_resume(
        suspension_id=record.suspension_id,
        user_id="user-2",
    ) is None
