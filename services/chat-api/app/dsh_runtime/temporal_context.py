"""Trusted, request-scoped time context for AgentKernel turns."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.dsh_runtime.contracts import TemporalContext


DEFAULT_USER_TIMEZONE = "UTC"


def normalize_user_timezone(value: str | None) -> str:
    """Validate an IANA timezone supplied by the authenticated user's client."""

    name = str(value or DEFAULT_USER_TIMEZONE).strip() or DEFAULT_USER_TIMEZONE
    try:
        ZoneInfo(name)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise ValueError(f"invalid IANA timezone: {name}") from exc
    return name


def build_temporal_context(
    timezone_name: str | None,
    *,
    now: datetime | None = None,
) -> TemporalContext:
    """Capture one immutable clock snapshot for an entire Agent turn."""

    zone_name = normalize_user_timezone(timezone_name)
    captured = now or datetime.now(timezone.utc)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("trusted runtime clock must be timezone-aware")
    captured_utc = captured.astimezone(timezone.utc)
    return TemporalContext(
        captured_at_utc=captured_utc,
        user_local_time=captured_utc.astimezone(ZoneInfo(zone_name)),
        user_timezone=zone_name,
    )
