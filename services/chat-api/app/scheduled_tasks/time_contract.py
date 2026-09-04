from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from .schedule import UTC, get_zone


SCHEDULE_VERSION = 2


def format_wall_datetime(value: datetime) -> str:
    return value.replace(tzinfo=None).isoformat(timespec="seconds")


def submitted_wall_time(value: datetime, timezone_name: str) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=None)
    return value.astimezone(get_zone(timezone_name)).replace(tzinfo=None)


def job_wall_time(doc: Mapping[str, Any]) -> datetime:
    value = doc["run_at"]
    if int(doc.get("schedule_version") or 0) >= SCHEDULE_VERSION:
        return value.replace(tzinfo=None)
    # Legacy UI submitted UTC instants; MongoDB returned those values as naive UTC.
    instant = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return instant.astimezone(get_zone(str(doc.get("timezone") or "UTC"))).replace(tzinfo=None)
