from __future__ import annotations

from typing import Any, Dict, List

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation

from .inventory import discover_fields
from .media_editor_candidates import rank_media_editors


_STRONGER_EDITOR_MARGIN = 100


def resolve_media_editor_ref(
    observation: Observation,
    target: Dict[str, Any],
    *,
    anchor: Any = None,
) -> str:
    """Resolve a current body editor for media insertion."""

    ranked = rank_media_editors(observation, target=target, anchor=anchor)
    if not ranked:
        return ""
    top = ranked[0]
    if (
        top.anchor_score > 0
        or top.field.semantic_role == "body"
        or len(ranked) == 1
        or top.score >= 250
        or top.score - ranked[1].score >= _STRONGER_EDITOR_MARGIN
    ):
        return top.field.ref
    return ""


def normalize_media_editor_ref(
    observation: Observation,
    requested_ref: str,
    *,
    target: Dict[str, Any] | None = None,
    anchor: Any = None,
) -> str:
    """Validate a requested ref and rebind it to the current body editor."""

    target = target or {}
    ranked = rank_media_editors(observation, target=target, anchor=anchor)
    if not ranked:
        return ""
    requested = next(
        (item for item in ranked if item.field.ref == requested_ref),
        None,
    )
    top = ranked[0]
    if requested is None:
        return resolve_media_editor_ref(
            observation,
            target,
            anchor=anchor,
        )
    if (
        top.field.ref != requested.field.ref
        and (
            top.anchor_score > requested.anchor_score
            or top.field.semantic_role == "body"
            or top.score - requested.score >= _STRONGER_EDITOR_MARGIN
        )
    ):
        return top.field.ref
    return requested.field.ref


def media_editor_candidate_payload(
    observation: Observation,
    *,
    target: Dict[str, Any] | None = None,
    anchor: Any = None,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    """Expose constrained, explainable candidates to the exploration model."""

    ranked = rank_media_editors(
        observation,
        target=target or {},
        anchor=anchor,
    )
    if ranked and ranked[0].score >= 250:
        ranked = [
            item for item in ranked
            if ranked[0].score - item.score < _STRONGER_EDITOR_MARGIN
        ]
    return [
        item.as_payload()
        for item in ranked[:max(0, limit)]
    ]


def media_editor_has_content(
    observation: Observation,
    ref: str,
) -> bool:
    field = next(
        (item for item in discover_fields(observation) if item.ref == ref),
        None,
    )
    return bool(field and field.current_value.strip())


def has_structured_empty_body_editor(
    observation: Observation,
    ref: str,
) -> bool:
    """Return true when media would outrun an empty article/message body."""

    fields = discover_fields(observation)
    selected = next((field for field in fields if field.ref == ref), None)
    if selected is None or selected.current_value.strip():
        return False
    if selected.semantic_role == "body":
        return True
    return any(
        field.ref != selected.ref and field.semantic_role == "title"
        for field in fields
    )


__all__ = [
    "has_structured_empty_body_editor",
    "media_editor_candidate_payload",
    "media_editor_has_content",
    "normalize_media_editor_ref",
    "resolve_media_editor_ref",
]
