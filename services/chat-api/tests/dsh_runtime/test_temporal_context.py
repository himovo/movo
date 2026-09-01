from datetime import datetime, timezone

import pytest

from app.dsh_runtime.temporal_context import build_temporal_context, normalize_user_timezone


def test_temporal_context_uses_user_iana_timezone_and_one_clock_snapshot() -> None:
    captured = datetime(2026, 8, 15, 10, 0, tzinfo=timezone.utc)
    context = build_temporal_context("Asia/Shanghai", now=captured)

    assert context.captured_at_utc == captured
    assert context.user_local_time.isoformat() == "2026-08-15T18:00:00+08:00"
    assert context.user_timezone == "Asia/Shanghai"


def test_temporal_context_supports_daylight_saving_timezones() -> None:
    winter = build_temporal_context(
        "America/New_York", now=datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    )
    summer = build_temporal_context(
        "America/New_York", now=datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
    )

    assert winter.user_local_time.isoformat() == "2026-01-15T07:00:00-05:00"
    assert summer.user_local_time.isoformat() == "2026-07-15T08:00:00-04:00"


def test_temporal_context_rejects_invalid_timezone_and_naive_clock() -> None:
    with pytest.raises(ValueError, match="invalid IANA timezone"):
        normalize_user_timezone("Mars/Olympus")
    with pytest.raises(ValueError, match="timezone-aware"):
        build_temporal_context("UTC", now=datetime(2026, 8, 15, 10, 0))
