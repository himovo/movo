from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


UTC = timezone.utc


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def get_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(str(name or "UTC"))
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"未知时区: {name}") from exc


def normalize_run_at(value: datetime, timezone_name: str) -> datetime:
    """Return an aware local datetime used as the recurrence anchor."""
    zone = get_zone(timezone_name)
    if value.tzinfo is None:
        return value.replace(tzinfo=zone)
    return value.astimezone(zone)


def next_run_at(
    *,
    schedule_kind: str,
    run_at: datetime,
    timezone_name: str,
    weekdays: list[int] | None = None,
    after_utc: datetime | None = None,
) -> datetime | None:
    anchor = normalize_run_at(run_at, timezone_name)
    after = (after_utc or utc_now()).replace(tzinfo=UTC).astimezone(anchor.tzinfo)
    if schedule_kind == "once":
        return anchor.astimezone(UTC).replace(tzinfo=None) if anchor > after else None

    if schedule_kind == "daily":
        candidate = after.replace(
            hour=anchor.hour,
            minute=anchor.minute,
            second=anchor.second,
            microsecond=0,
        )
        if candidate <= after:
            candidate += timedelta(days=1)
        return candidate.astimezone(UTC).replace(tzinfo=None)

    if schedule_kind == "weekly":
        allowed = sorted(set(weekdays or [anchor.weekday()]))
        for offset in range(0, 8):
            day = after + timedelta(days=offset)
            if day.weekday() not in allowed:
                continue
            candidate = day.replace(
                hour=anchor.hour,
                minute=anchor.minute,
                second=anchor.second,
                microsecond=0,
            )
            if candidate > after:
                return candidate.astimezone(UTC).replace(tzinfo=None)
    raise ValueError(f"不支持的调度类型: {schedule_kind}")
