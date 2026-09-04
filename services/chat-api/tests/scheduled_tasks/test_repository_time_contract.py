from datetime import datetime

from app.scheduled_tasks.repository import serialize_job
from app.scheduled_tasks.time_contract import SCHEDULE_VERSION


def _job(**overrides):
    return {
        "_id": "job-1",
        "name": "test",
        "prompt": "run",
        "schedule_kind": "daily",
        "timezone": "Asia/Shanghai",
        "run_at": datetime(2026, 9, 5, 9, 15, 30),
        "enabled": True,
        **overrides,
    }


def test_v2_anchor_is_serialized_as_wall_time_without_utc_suffix() -> None:
    serialized = serialize_job(_job(schedule_version=SCHEDULE_VERSION))
    assert serialized["run_at"] == "2026-09-05T09:15:30"


def test_legacy_utc_anchor_is_migrated_to_the_task_wall_time() -> None:
    serialized = serialize_job(_job(run_at=datetime(2026, 9, 5, 1, 15, 30)))
    assert serialized["run_at"] == "2026-09-05T09:15:30"
