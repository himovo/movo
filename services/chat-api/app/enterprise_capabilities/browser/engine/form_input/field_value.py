"""Normalize field values emitted by browser DOM observations."""
from __future__ import annotations

import re
from typing import Any, Mapping


def current_field_value(element: Mapping[str, Any], *, placeholder: str = "") -> str:
    """Return user content without treating a rich-editor hint as content."""

    value = str(element.get("value") or "")
    if not value.strip():
        return ""
    content_editable = bool(
        element.get("contentEditable") or element.get("content_editable")
    )
    decorative = bool(
        element.get("placeholderDecorative")
        or element.get("placeholder_decorative")
    )
    if (
        content_editable
        and decorative
        and _normalized(value) == _normalized(placeholder)
    ):
        return ""
    return value


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


__all__ = ["current_field_value"]
