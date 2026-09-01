from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation

from .contracts import FieldDescriptor
from .inventory import discover_fields


_MIN_EDITOR_SCORE = 60


@dataclass(frozen=True)
class RankedMediaEditor:
    field: FieldDescriptor
    score: int
    anchor_score: int

    def as_payload(self) -> Dict[str, Any]:
        raw = self.field.raw
        return {
            "ref": self.field.ref,
            "field_key": self.field.field_key,
            "semantic_role": self.field.semantic_role or "unknown",
            "label": self.field.semantic_label,
            "control_kind": self.field.control_kind,
            "scope_id": self.field.scope_id,
            "frame_depth": _int_value(raw.get("frameDepth")),
            "width": _number(raw.get("width")),
            "height": _number(raw.get("height")),
            "has_value": bool(self.field.current_value.strip()),
            "score": self.score,
        }


def rank_media_editors(
    observation: Observation,
    *,
    target: Dict[str, Any],
    anchor: Any,
) -> List[RankedMediaEditor]:
    """Rank body-like editors from the shared live field inventory."""

    target_scope = str(target.get("scopeId") or target.get("scope_id") or "")
    anchor_dict = anchor if isinstance(anchor, dict) else {}
    ranked: List[RankedMediaEditor] = []
    for field in discover_fields(observation):
        if not _eligible_editor(field):
            continue
        anchor_score = _anchor_editor_score(field.raw, anchor_dict)
        score = _editor_score(
            field,
            target_scope=target_scope,
            anchor_score=anchor_score,
        )
        if score >= _MIN_EDITOR_SCORE:
            ranked.append(RankedMediaEditor(
                field=field,
                score=score,
                anchor_score=anchor_score,
            ))
    ranked.sort(key=lambda item: (-item.score, item.field.ref))
    return ranked


def _eligible_editor(field: FieldDescriptor) -> bool:
    raw = field.raw
    return (
        field.control_kind in {"rich_text", "multiline"}
        and bool(field.ref)
        and raw.get("editable")
        and not raw.get("disabled")
        and not raw.get("searchContext")
        and not raw.get("search_context")
        and raw.get("visible") is not False
    )


def _editor_score(
    field: FieldDescriptor,
    *,
    target_scope: str,
    anchor_score: int,
) -> int:
    raw = field.raw
    role = field.semantic_role
    score = 120 if field.control_kind == "rich_text" else 80
    if role == "body":
        score += 500
    elif role:
        score -= 700
    score += anchor_score

    if target_scope and field.scope_id == target_scope:
        score += 60
    frame_hosts = {
        str(item) for item in list(raw.get("frameHostScopeIds") or [])
        if str(item)
    }
    if target_scope and target_scope in frame_hosts:
        score += 60

    height = _number(raw.get("height"))
    width = _number(raw.get("width"))
    if height >= 120:
        score += 120
    elif height >= 60:
        score += 45
    elif 0 < height <= 48:
        score -= 25
    if width >= 300:
        score += 20
    if height * width >= 100_000:
        score += 80
    if _int_value(raw.get("frameDepth")) > 0:
        score += 35
    if str(raw.get("tag") or "").strip().lower() == "body":
        score += 60
    if raw.get("multiline"):
        score += 25
    if raw.get("focused"):
        score += 15
    return score


def _anchor_editor_score(
    element: Dict[str, Any],
    anchor: Dict[str, Any],
) -> int:
    content = _compact_value(element.get("value") or element.get("text") or "")
    if not content or not anchor:
        return 0
    after = _compact_value(anchor.get("after_text"))
    before = _compact_value(anchor.get("before_text"))
    score = 0
    if after:
        if after in content:
            score += 500
        elif _anchor_fragment(after, from_end=True) in content:
            score += 300
    if before:
        if before in content:
            score += 500
        elif _anchor_fragment(before, from_end=False) in content:
            score += 300
    return score


def _anchor_fragment(value: str, *, from_end: bool) -> str:
    length = min(80, len(value))
    if length < 12:
        return value
    return value[-length:] if from_end else value[:length]


def _compact_value(value: Any) -> str:
    return "".join(str(value or "").split())


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


__all__ = ["RankedMediaEditor", "rank_media_editors"]
