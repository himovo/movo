from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_VOLATILE_QUERY_KEY = re.compile(
    r"^(?:access_?token|refresh_?token|token|auth|authorization|session|session_?id|sid|"
    r"timestamp|time_?stamp|ts|nonce|signature|sign|ticket|csrf|xsrf|expires?|expiry)$",
    re.I,
)


def is_volatile_query_key(key: str) -> bool:
    return bool(_VOLATILE_QUERY_KEY.fullmatch(str(key or "").strip()))


def portable_navigation_url(url: str) -> str:
    """Remove session/nonce material while retaining business route parameters."""
    try:
        parsed = urlsplit(str(url or ""))
    except ValueError:
        return ""
    if not parsed.scheme or not parsed.netloc:
        return str(url or "").strip()
    query = urlencode([
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not is_volatile_query_key(key)
    ], doseq=True, safe="/")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))


def navigation_url_is_portable(url: str) -> bool:
    try:
        return not any(
            is_volatile_query_key(key)
            for key, _ in parse_qsl(urlsplit(str(url or "")).query, keep_blank_values=True)
        )
    except ValueError:
        return False


__all__ = ["is_volatile_query_key", "navigation_url_is_portable", "portable_navigation_url"]
