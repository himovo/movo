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
        return localize_wall_time(value, zone)
    return value.astimezone(zone)


def localize_wall_time(value: datetime, zone: ZoneInfo) -> datetime:
    """Resolve a wall time deterministically: first fold, or shift through a DST gap."""
    naive = value.replace(tzinfo=None)
    candidate = naive.replace(tzinfo=zone, fold=0)
    roundtrip = candidate.astimezone(UTC).astimezone(zone)
    return candidate if roundtrip.replace(tzinfo=None) == naive else roundtrip


def _utc_aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _candidate(day, anchor: datetime, zone: ZoneInfo) -> datetime:
    wall = datetime.combine(day, anchor.time().replace(tzinfo=None))
    return localize_wall_time(wall.replace(microsecond=0), zone)


def next_run_at(
    *,
    schedule_kind: str,
    run_at: datetime,
    timezone_name: str,
    weekdays: list[int] | None = None,
    after_utc: datetime | None = None,
) -> datetime | None:
    anchor = normalize_run_at(run_at, timezone_name)
    after_instant = _utc_aware(after_utc or utc_now())
    after = after_instant.astimezone(anchor.tzinfo)
    if schedule_kind == "once":
        return anchor.astimezone(UTC).replace(tzinfo=None) if anchor.astimezone(UTC) > after_instant else None

    if schedule_kind == "daily":
        first_day = max(after.date(), anchor.date())
        for offset in range(0, 3):
            candidate = _candidate(first_day + timedelta(days=offset), anchor, anchor.tzinfo)
            if candidate.astimezone(UTC) > after_instant and candidate.astimezone(UTC) >= anchor.astimezone(UTC):
                return candidate.astimezone(UTC).replace(tzinfo=None)

    if schedule_kind == "weekly":
        allowed = sorted(set(weekdays or [anchor.weekday()]))
        first_day = max(after.date(), anchor.date())
        for offset in range(0, 15):
            day = first_day + timedelta(days=offset)
            if day.weekday() not in allowed:
                continue
            candidate = _candidate(day, anchor, anchor.tzinfo)
            if candidate.astimezone(UTC) > after_instant and candidate.astimezone(UTC) >= anchor.astimezone(UTC):
                return candidate.astimezone(UTC).replace(tzinfo=None)
    raise ValueError(f"不支持的调度类型: {schedule_kind}")
