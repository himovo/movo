from __future__ import annotations

from collections import OrderedDict
from typing import Any, Dict, Iterable, List

from .contracts import FieldDescriptor


def element_scope_id(element: Dict[str, Any]) -> str:
    scope_id = str(element.get("scopeId") or element.get("scope_id") or "").strip()
    frame_host_scope_ids = _frame_host_scope_ids(element)
    if frame_host_scope_ids and element.get("scopeLockable") is False:
        return frame_host_scope_ids[-1]
    if scope_id:
        return scope_id
    if frame_host_scope_ids:
        return frame_host_scope_ids[-1]
    return f"__page__:{int(element.get('frameDepth') or 0)}"


def group_fields_by_scope(fields: Iterable[FieldDescriptor]) -> Dict[str, List[FieldDescriptor]]:
    grouped: Dict[str, List[FieldDescriptor]] = OrderedDict()
    for field in fields:
        grouped.setdefault(field.scope_id or f"__page__:{int(field.raw.get('frameDepth') or 0)}", []).append(field)
    return grouped


def elements_in_scope(elements: Iterable[Any], scope_id: str) -> List[Dict[str, Any]]:
    return [
        item for item in elements
        if isinstance(item, dict) and element_scope_id(item) == scope_id
    ]


def has_explicit_scope(scope_id: str) -> bool:
    return bool(scope_id and not scope_id.startswith("__page__:"))


def _frame_host_scope_ids(element: Dict[str, Any]) -> tuple[str, ...]:
    raw = (
        element.get("frameHostScopeIds")
        or element.get("frame_host_scope_ids")
        or []
    )
    if not isinstance(raw, (list, tuple)):
        return ()
    return tuple(dict.fromkeys(
        str(item).strip()
        for item in raw
        if str(item).strip()
    ))


__all__ = [
    "element_scope_id",
    "elements_in_scope",
    "group_fields_by_scope",
    "has_explicit_scope",
]
