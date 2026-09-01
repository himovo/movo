from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, Optional


_ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200d\u2060\ufeff]")
_WHITESPACE_RE = re.compile(r"\s+")


def field_values_equivalent(
    actual: Any,
    expected: Any,
    *,
    target: Optional[Dict[str, Any]] = None,
) -> bool:
    """Compare field values without losing rich-editor structural semantics."""

    if _plain_value(actual) == _plain_value(expected):
        return True
    if not _is_rich_text_target(target):
        return False
    actual_compact = _rich_text_value(actual)
    expected_compact = _rich_text_value(expected)
    return bool(expected_compact and actual_compact == expected_compact)


def _plain_value(value: Any) -> str:
    normalized = _normalized_unicode(value)
    return _WHITESPACE_RE.sub(" ", normalized).strip().casefold()


def _rich_text_value(value: Any) -> str:
    return _WHITESPACE_RE.sub("", _normalized_unicode(value))


def _normalized_unicode(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    return _ZERO_WIDTH_RE.sub("", normalized)


def _is_rich_text_target(target: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(target, dict):
        return False
    mode = str(
        target.get("contentEditableMode")
        or target.get("content_editable_mode")
        or ""
    ).strip().lower()
    if mode == "plaintext-only":
        return False
    return bool(target.get("contentEditable") or target.get("content_editable"))


__all__ = ["field_values_equivalent"]
