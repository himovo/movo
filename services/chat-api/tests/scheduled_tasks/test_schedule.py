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


def test_daily_schedule_does_not_run_before_anchor_date() -> None:
    result = next_run_at(
        schedule_kind="daily",
        run_at=datetime(2026, 10, 1, 9, 0),
        timezone_name="Asia/Shanghai",
        after_utc=datetime(2026, 9, 4, 0, 0),
    )
    assert result == datetime(2026, 10, 1, 1, 0)


def test_weekly_schedule_starts_on_first_allowed_day_after_anchor() -> None:
    result = next_run_at(
        schedule_kind="weekly",
        run_at=datetime(2026, 10, 1, 9, 0),
        timezone_name="Asia/Shanghai",
        weekdays=[0],
        after_utc=datetime(2026, 9, 4, 0, 0),
    )
    assert result == datetime(2026, 10, 5, 1, 0)


def test_nonexistent_dst_time_shifts_forward_by_the_gap() -> None:
    result = next_run_at(
        schedule_kind="daily",
        run_at=datetime(2026, 3, 7, 2, 30),
        timezone_name="America/New_York",
        after_utc=datetime(2026, 3, 8, 5, 0),
    )
    # 02:30 does not exist on this date; the documented policy executes at 03:30 EDT.
    assert result == datetime(2026, 3, 8, 7, 30)


def test_ambiguous_dst_time_uses_the_first_fold() -> None:
    result = next_run_at(
        schedule_kind="daily",
        run_at=datetime(2026, 10, 31, 1, 30),
        timezone_name="America/New_York",
        after_utc=datetime(2026, 11, 1, 4, 0),
    )
    assert result == datetime(2026, 11, 1, 5, 30)
