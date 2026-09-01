from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlsplit

from .url_portability import is_volatile_query_key


_OPAQUE_SEGMENT = re.compile(
    r"^(?:\d{3,}|[0-9a-f]{8,}|[A-Za-z0-9_-]{20,})$",
    re.I,
)


def url_shape(url: str) -> str:
    """Stable, value-free route identity used as a replay precondition."""
    try:
        parsed = urlsplit(str(url or ""))
    except ValueError:
        return ""
    if not parsed.hostname:
        return str(url or "").strip().casefold()
    segments = [
        "{id}" if _OPAQUE_SEGMENT.fullmatch(segment) else segment.casefold()
        for segment in parsed.path.split("/")
    ]
    path = "/".join(segments) or "/"
    keys = sorted({
        str(key).casefold()
        for key, _ in parse_qsl(parsed.query, keep_blank_values=True)
        if not is_volatile_query_key(key)
    })
    suffix = f"?{'&'.join(keys)}" if keys else ""
    return f"{parsed.hostname.casefold().removeprefix('www.')}{path}{suffix}"


def same_url_shape(actual_url: str, expected_shape: str) -> bool:
    return not expected_shape or url_shape(actual_url) == expected_shape


__all__ = ["same_url_shape", "url_shape"]
