from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def utc_iso(value: Any) -> str:
    if not isinstance(value, datetime):
        return ""
    normalized = value
    if normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=timezone.utc)
    return normalized.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
