"""Resolve an action's purpose from confirmed fields it directly owns."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Tuple

from .interaction_relation import resolve_field_action_relation


@dataclass(frozen=True)
class InteractionPurposeResolution:
    purpose: str = ""
    source: str = ""
    matched_indexes: Tuple[int, ...] = ()


def resolve_interaction_purpose(
    *,
    action_target: Dict[str, Any] | None,
    filled_targets: Iterable[Dict[str, Any]],
) -> InteractionPurposeResolution:
    """Return a purpose only when every related confirmed field agrees.

    The sidecar records native form ownership and direct compact-component
    field associations. Scope ancestry remains a compatibility fallback, but
    broad page scopes are excluded by ``scope_identity``.
    """
    targets = [dict(item) for item in filled_targets if isinstance(item, dict)]
    direct = _field_purpose(action_target or {})
    if direct:
        return InteractionPurposeResolution(purpose=direct, source="action_semantics")
    if not targets:
        return InteractionPurposeResolution()
    if action_target is None:
        purpose = _field_purpose(targets[-1])
        return InteractionPurposeResolution(
            purpose=purpose,
            source="latest_confirmed_field" if purpose else "",
            matched_indexes=(len(targets) - 1,) if purpose else (),
        )

    related = [
        (index, target, source)
        for index, target in enumerate(targets)
        if (source := _relation_source(target, action_target))
    ]
    if not related:
        return InteractionPurposeResolution()
    purposes = [_field_purpose(target) for _, target, _ in related]
    # A mixed-purpose form is ambiguous. In particular, a header search field
    # must not downgrade a submit button that also owns a business text area.
    if any(not purpose for purpose in purposes) or len(set(purposes)) != 1:
        return InteractionPurposeResolution()
    return InteractionPurposeResolution(
        purpose=purposes[0],
        source="+".join(dict.fromkeys(source for _, _, source in related)),
        matched_indexes=tuple(index for index, _, _ in related),
    )


def _relation_source(field: Dict[str, Any], action: Dict[str, Any]) -> str:
    relation = resolve_field_action_relation(field, action)
    return relation.source if relation.related else ""


def _field_purpose(target: Dict[str, Any]) -> str:
    semantic = str(target.get("semanticPurpose") or "").strip().lower()
    if semantic:
        return semantic
    if target.get("searchContext"):
        return "search"
    role = str(target.get("role") or "").strip().lower()
    if role == "searchbox":
        return "search"
    scope_role = str(target.get("scopeRole") or target.get("formOwnerRole") or "").strip().lower()
    return "search" if scope_role == "search" else ""


__all__ = [
    "InteractionPurposeResolution",
    "resolve_interaction_purpose",
]
