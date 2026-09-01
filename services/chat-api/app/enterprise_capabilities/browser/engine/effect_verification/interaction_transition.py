"""Detect non-committing UI transitions around a browser click.

The effect classifier runs before a click and can occasionally confuse an
entry action (open an editor/form) with the final commit. Post-click DOM state
is stronger evidence: a newly exposed editable surface means the workflow has
entered an input phase and no business side effect has been committed yet.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


_FIELD_ROLES = {"textbox", "searchbox", "combobox", "spinbutton"}
_DIALOG_ROLES = {"dialog", "alertdialog", "drawer"}
_OUTCOME_TEXT = re.compile(
    r"(成功|失败|已完成|已提交|已发布|已发送|错误|被拒绝|"
    r"success|failed|completed|submitted|published|sent|error|rejected)",
    re.I,
)


@dataclass(frozen=True)
class InteractionTransition:
    kind: str
    reason: str


def has_editable_surface(observation: Observation) -> bool:
    return bool(_editable_fields(observation.elements))


def detect_interaction_transition(
    *, before: Observation, after: Observation,
) -> InteractionTransition | None:
    before_fields = _editable_fields(before.elements)
    after_fields = _editable_fields(after.elements)
    if not after_fields or _has_explicit_outcome(after):
        return None

    before_signatures = {_field_signature(item) for item in before_fields}
    after_signatures = {_field_signature(item) for item in after_fields}
    new_signatures = after_signatures - before_signatures
    field_count_increased = len(after_fields) > len(before_fields)
    dialog_opened = _dialog_count(after.elements) > _dialog_count(before.elements)

    if field_count_increased or dialog_opened or (not before_fields and new_signatures):
        detail = (
            f"editable fields {len(before_fields)} -> {len(after_fields)}; "
            f"new semantic fields={len(new_signatures)}; dialog_opened={dialog_opened}"
        )
        return InteractionTransition(kind="editor_opened", reason=detail)
    return None


def _editable_fields(elements: Iterable[Dict[str, Any]]) -> list[Dict[str, Any]]:
    return [
        item for item in elements
        if isinstance(item, dict)
        and not item.get("disabled")
        and (
            bool(item.get("editable"))
            or str(item.get("role") or "").strip().lower() in _FIELD_ROLES
        )
    ]


def _field_signature(item: Dict[str, Any]) -> str:
    return "\x00".join(
        str(item.get(key) or "").strip().lower()
        for key in ("role", "name", "placeholder", "type", "description")
    )


def _dialog_count(elements: Iterable[Dict[str, Any]]) -> int:
    return sum(
        1 for item in elements
        if isinstance(item, dict)
        and str(item.get("role") or "").strip().lower() in _DIALOG_ROLES
    )


def _has_explicit_outcome(observation: Observation) -> bool:
    for effect in list(observation.effects or []):
        if not isinstance(effect, dict) or effect.get("kind") not in {"dom_added", "dom_changed"}:
            continue
        role = str(effect.get("role") or "").strip().lower()
        text = str(effect.get("text") or "").strip()
        if role in {"alert", "status"} and _OUTCOME_TEXT.search(text):
            return True
    return False
