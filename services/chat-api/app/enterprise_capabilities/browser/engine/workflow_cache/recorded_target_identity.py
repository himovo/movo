from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from typing import Any, Dict, Iterable

from .page_state import url_shape


_SEMANTIC_FIELDS = (
    "role", "name", "text", "description", "placeholder",
    "semanticPurpose", "scopeName", "scopeRole", "contentContextId",
    "hasPopup", "type", "accept",
    "activationVerified",
)
_VALUE_BEARING_EVENTS = {"fill", "select"}
_TAG = re.compile(r"<[^>]+>")
_TARGET_ALIASES = {
    "aria_label": "name",
    "ancestor_contains_text": "scopeName",
    "ancestor_role": "scopeRole",
}


def stabilize_recorded_target_identities(
    events: Iterable[Dict[str, Any]],
    *,
    identity_observations: Iterable[Dict[str, Any]] = (),
) -> list[Dict[str, Any]]:
    """Carry a control's stable identity across value-driven DOM mutations.

    Rich editors and reactive inputs often replace their accessible name with
    the value just entered.  The recorder still observes the same DOM control,
    but a later event then appears to have only a dynamic locator.  Remembering
    semantic fields by exact physical identity lets replay use the stable label
    seen before editing without weakening locator admission globally.

    Identity is deliberately strict: selectors are never matched fuzzily, and
    page shape, frame, and tab participate in the key.  This prevents semantics
    leaking between similar controls or documents.
    """
    identities: dict[tuple[str, str, str, str], Dict[str, Any]] = {}
    written_values: dict[tuple[str, str, str, str], set[str]] = {}

    def stabilize(event: Dict[str, Any]) -> Dict[str, Any]:
        target = event.get("target") if isinstance(event.get("target"), dict) else {}
        key = _control_key(event, target)
        if key is None:
            return event

        values = written_values.setdefault(key, set())
        if str(event.get("type") or "").strip().casefold() in _VALUE_BEARING_EVENTS:
            normalized = _normalized_written_value(event.get("value"))
            if normalized:
                values.add(normalized)

        cleaned = _canonical_target(target)
        for field in ("name", "text", "description", "placeholder", "scopeName"):
            if _contains_written_value(cleaned.get(field), values):
                cleaned.pop(field, None)

        remembered = identities.get(key, {})
        for field in _SEMANTIC_FIELDS:
            if cleaned.get(field) in (None, "", False) and remembered.get(field) not in (
                None, "", False,
            ):
                cleaned[field] = remembered[field]

        stable = dict(remembered)
        for field in _SEMANTIC_FIELDS:
            value = cleaned.get(field)
            if value in (None, "", False) or _contains_written_value(value, values):
                continue
            stable[field] = value
        identities[key] = stable

        updated = dict(event)
        updated["target"] = cleaned
        return updated

    # Raw observations seed identity memory even if compaction later removes
    # them. They do not replace the events returned to the caller.
    for observation in _ordered_events(identity_observations):
        stabilize(observation)
    return [stabilize(event) for event in _ordered_events(events)]


def _ordered_events(events: Iterable[Dict[str, Any]]) -> list[Dict[str, Any]]:
    return sorted(
        (dict(item) for item in events if isinstance(item, dict)),
        key=lambda item: int(item.get("_recording_order", item.get("sequence")) or 0),
    )


def _control_key(
    event: Dict[str, Any],
    target: Dict[str, Any],
) -> tuple[str, str, str, str] | None:
    selector = str(target.get("selector") or "").strip()
    if not selector:
        return None
    page = url_shape(str(event.get("before_url") or event.get("url") or ""))
    frame = str(target.get("frameDepth") or 0)
    tab = str(event.get("before_tab_id") or event.get("after_tab_id") or "")
    return tab, page, frame, selector


def _canonical_target(target: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(target)
    for alias, canonical in _TARGET_ALIASES.items():
        value = result.pop(alias, None)
        if result.get(canonical) in (None, "", False) and value not in (None, "", False):
            result[canonical] = value
    return result


def _contains_written_value(value: Any, written_values: set[str]) -> bool:
    normalized = _normalized_text(value)
    return bool(
        normalized
        and any(normalized == item or item in normalized for item in written_values)
    )


def _normalized_text(value: Any) -> str:
    raw = html.unescape(str(value or ""))
    raw = _TAG.sub(" ", raw)
    return " ".join(raw.replace("\u200b", "").split()).casefold()


def _normalized_written_value(value: Any) -> str:
    raw = str(value or "")
    if "<" not in raw or ">" not in raw:
        return _normalized_text(raw)
    parser = _EditableTextParser()
    try:
        parser.feed(raw)
        parser.close()
    except Exception:
        return _normalized_text(raw)
    return _normalized_text(" ".join(parser.parts))


class _EditableTextParser(HTMLParser):
    """Extract authored text while excluding non-editable UI decorations."""

    _VOID_ELEMENTS = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {str(key).casefold(): str(value or "").casefold() for key, value in attrs}
        ignored = (
            values.get("contenteditable") == "false"
            or values.get("aria-hidden") == "true"
            or "hidden" in values
        )
        if tag.casefold() not in self._VOID_ELEMENTS and (self._ignored_depth or ignored):
            self._ignored_depth += 1

    def handle_startendtag(self, _tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        return

    def handle_endtag(self, _tag: str) -> None:
        if self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth and data:
            self.parts.append(data)


__all__ = ["stabilize_recorded_target_identities"]
