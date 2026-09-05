from __future__ import annotations

import html
import re
from typing import Any, Iterable


_POSITIONAL_SELECTOR = re.compile(r":nth-(?:child|of-type)\s*\(", re.I)
_TAG = re.compile(r"<[^>]+>")


def portable_locator(
    locator: dict[str, Any],
    *,
    sensitive_values: Iterable[str] = (),
) -> dict[str, Any]:
    result = dict(locator or {})
    sensitive = {_text(value) for value in sensitive_values if _text(value)}
    for key in ("name", "text", "description", "placeholder", "scopeName"):
        value = _text(result.get(key))
        # A locator is contaminated when it equals or contains the submitted
        # value.  The inverse is intentionally not true: a stable field label
        # such as "正文" may legitimately be a substring of the entered value.
        if value and any(value == item or item in value for item in sensitive):
            result.pop(key, None)
    selector = str(result.get("selector") or "").strip()
    if selector and _POSITIONAL_SELECTOR.search(selector) and _semantic_strength(result) >= 16:
        result.pop("selector", None)
    return result


def locator_is_portable(locator: dict[str, Any]) -> bool:
    values = dict(locator or {})
    selector = str(values.get("selector") or "").strip()
    if selector and not _POSITIONAL_SELECTOR.search(selector):
        return True
    return _semantic_strength(values) >= 16


def _semantic_strength(locator: dict[str, Any]) -> int:
    score = 0
    if locator.get("role"):
        score += 8
    if locator.get("name"):
        score += 16
    if locator.get("text"):
        score += 10
    if locator.get("placeholder"):
        score += 14
    if locator.get("semanticPurpose"):
        score += 18
    if str(locator.get("type") or "").casefold() == "file":
        score += 18
    if locator.get("accept"):
        score += 8
    if locator.get("scopeName"):
        score += 10
    if locator.get("scopeRole"):
        score += 4
    if locator.get("contentContextId"):
        score += 24
    return score


def _text(value: Any) -> str:
    raw = html.unescape(str(value or ""))
    raw = _TAG.sub(" ", raw)
    return " ".join(raw.replace("\u200b", "").split()).casefold()


__all__ = ["locator_is_portable", "portable_locator"]
