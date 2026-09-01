from datetime import datetime

from app.scheduled_tasks.schedule import next_run_at


def test_daily_schedule_uses_requested_timezone() -> None:
    result = next_run_at(
        schedule_kind="daily",
        run_at=datetime(2026, 8, 6, 9, 30),
        timezone_name="Asia/Shanghai",
        after_utc=datetime(2026, 8, 6, 2, 0),
    )
    assert result == datetime(2026, 8, 7, 1, 30)


def test_weekly_schedule_selects_next_enabled_weekday() -> None:
    # 2026-08-06 is Thursday; Monday=0 and Friday=4.
    result = next_run_at(
        schedule_kind="weekly",
        run_at=datetime(2026, 8, 6, 9, 0),
        timezone_name="Asia/Shanghai",
        weekdays=[0, 4],
        after_utc=datetime(2026, 8, 6, 2, 0),
    )
    assert result == datetime(2026, 8, 7, 1, 0)


def test_expired_once_schedule_has_no_next_run() -> None:
    result = next_run_at(
        schedule_kind="once",
        run_at=datetime(2026, 8, 6, 9, 0),
        timezone_name="Asia/Shanghai",
        after_utc=datetime(2026, 8, 6, 2, 0),
    )
    assert result is None
