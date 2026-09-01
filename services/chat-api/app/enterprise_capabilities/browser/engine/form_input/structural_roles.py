"""Infer stable title/body roles from one live business-form structure."""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .contracts import FieldDescriptor


_EDITOR_KINDS = {"text", "multiline", "rich_text"}


def annotate_structural_field_roles(
    fields: Iterable[FieldDescriptor],
) -> list[FieldDescriptor]:
    """Add conservative role hints when framework editors omit labels.

    The inference is local to one resolved form scope. It does not depend on a
    website, selector, or placeholder value.
    """

    result = list(fields)
    grouped: dict[str, list[FieldDescriptor]] = defaultdict(list)
    for field in result:
        grouped[field.scope_id].append(field)

    for scoped_fields in grouped.values():
        body = next(
            (field for field in scoped_fields if field.semantic_role == "body"),
            None,
        ) or _infer_body(scoped_fields)
        if body is None:
            continue
        if body.semantic_role != "body":
            _set_role(body, "body")
        title = _infer_title(scoped_fields, body)
        if title is not None:
            _set_role(title, "title")
    return result


def _infer_body(fields: list[FieldDescriptor]) -> FieldDescriptor | None:
    ranked = sorted(
        (
            (_body_score(field), index, field)
            for index, field in enumerate(fields)
            if _eligible(field)
        ),
        key=lambda item: (-item[0], item[1]),
    )
    if not ranked or ranked[0][0] < 260:
        return None
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 90:
        return None
    return ranked[0][2]


def _infer_title(
    fields: list[FieldDescriptor],
    body: FieldDescriptor,
) -> FieldDescriptor | None:
    if any(field.semantic_role == "title" for field in fields):
        return None
    body_index = fields.index(body)
    ranked = sorted(
        (
            (_title_score(field, body=body, before_body=index < body_index), index, field)
            for index, field in enumerate(fields)
            if field is not body and _eligible(field)
        ),
        key=lambda item: (-item[0], item[1]),
    )
    if not ranked or ranked[0][0] < 180:
        return None
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 70:
        return None
    return ranked[0][2]


def _eligible(field: FieldDescriptor) -> bool:
    raw = field.raw
    return (
        field.control_kind in _EDITOR_KINDS
        and not field.sensitive
        and raw.get("visible") is not False
        and not raw.get("disabled")
        and not raw.get("searchContext")
        and not raw.get("search_context")
        and field.role != "searchbox"
    )


def _body_score(field: FieldDescriptor) -> int:
    raw = field.raw
    height = _number(raw.get("height"))
    width = _number(raw.get("width"))
    score = 120 if field.control_kind == "rich_text" else 65
    if field.control_kind == "text":
        score -= 90
    if height >= 120:
        score += 160
    elif 0 < height <= 64:
        score -= 100
    if width * height >= 100_000:
        score += 100
    if _integer(raw.get("frameDepth")) > 0:
        score += 80
    if str(raw.get("tag") or "").strip().lower() == "body":
        score += 110
    if raw.get("multiline"):
        score += 45
    return score


def _title_score(
    field: FieldDescriptor,
    *,
    body: FieldDescriptor,
    before_body: bool,
) -> int:
    raw = field.raw
    height = _number(raw.get("height"))
    width = _number(raw.get("width"))
    score = 110 if field.control_kind == "text" else 75
    if 0 < height <= 72:
        score += 80
    elif height >= 160:
        score -= 120
    if width >= 160:
        score += 20
    if before_body:
        score += 45
    if _integer(raw.get("frameDepth")) < _integer(body.raw.get("frameDepth")):
        score += 55
    if str(raw.get("tag") or "").strip().lower() in {"input", "textarea"}:
        score += 25
    return score


def _set_role(field: FieldDescriptor, role: str) -> None:
    field.raw["inferredFieldRole"] = role
    field.raw["inferredFieldRoleSource"] = "form_structure"


def _number(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _integer(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


__all__ = ["annotate_structural_field_roles"]
