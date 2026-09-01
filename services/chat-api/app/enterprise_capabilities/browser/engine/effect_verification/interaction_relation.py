"""Canonical relationship resolution between a form field and an action."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Literal

from .scope_identity import scope_identity, scopes_related, selector_contains


RelationStatus = Literal["related", "unrelated", "unknown"]
_MEANINGFUL_BOUNDARY_ROLES = {
    "article",
    "dialog",
    "form",
    "main",
    "region",
    "search",
    "section",
}


@dataclass(frozen=True)
class InteractionRelation:
    status: RelationStatus = "unknown"
    source: str = ""

    @property
    def related(self) -> bool:
        return self.status == "related"


def resolve_field_action_relation(
    field: Dict[str, Any],
    action: Dict[str, Any],
) -> InteractionRelation:
    """Resolve one field/action relationship without conflating unknown with false."""
    if _frame_depth(field) != _frame_depth(action):
        field_scope = scope_identity(field)
        action_scope = scope_identity(action)
        if (
            field_scope is not None
            and action_scope is not None
            and scopes_related(field_scope, action_scope)
        ):
            return InteractionRelation(
                status="related",
                source="frame_host_scope",
            )
        host_component_relation = _cross_frame_host_component_relation(
            inner=field,
            outer=action,
        )
        if host_component_relation.status != "unknown":
            return host_component_relation
        host_component_relation = _cross_frame_host_component_relation(
            inner=action,
            outer=field,
        )
        if host_component_relation.status != "unknown":
            return host_component_relation
        return InteractionRelation(status="unrelated", source="different_frame")

    field_selector = _selector(field)
    associated = _associated_field_selectors(action)
    if field_selector and field_selector in associated:
        return InteractionRelation(status="related", source="direct_dom_association")
    if (
        associated
        and field_selector
        and _field_association_kind(action) != "component"
    ):
        return InteractionRelation(
            status="unrelated",
            source="direct_dom_association",
        )

    field_owner = _form_owner(field)
    action_owner = _form_owner(action)
    if field_owner and action_owner:
        return InteractionRelation(
            status="related" if field_owner == action_owner else "unrelated",
            source="form_owner",
        )

    field_component = _component_owner(field)
    action_component = _component_owner(action)
    if (
        field_component
        and action_component
        and _component_owner_associable(field)
        and _component_owner_associable(action)
        and field_component == action_component
        and _component_contains_target(field_component, field)
        and _component_contains_target(action_component, action)
    ):
        return InteractionRelation(
            status="related",
            source="interaction_component_owner",
        )

    field_scope = scope_identity(field)
    action_scope = scope_identity(action)
    if field_scope is not None and action_scope is not None:
        return InteractionRelation(
            status="related" if scopes_related(field_scope, action_scope) else "unrelated",
            source="interaction_scope",
        )

    if _structural_scope_ancestry(field, action):
        return InteractionRelation(
            status="related",
            source="structural_scope_ancestry",
        )

    return InteractionRelation()


def resolve_action_fields_relation(
    *,
    action: Dict[str, Any],
    fields: Iterable[Dict[str, Any]],
) -> InteractionRelation:
    """Aggregate field evidence for one action using conservative three-state logic."""
    field_list = [dict(item) for item in fields if isinstance(item, dict)]
    if not field_list:
        return InteractionRelation()

    relations = [
        resolve_field_action_relation(field, action)
        for field in field_list
    ]
    related = [relation for relation in relations if relation.related]
    if related:
        return InteractionRelation(
            status="related",
            source="+".join(dict.fromkeys(item.source for item in related if item.source)),
        )
    if relations and all(item.status == "unrelated" for item in relations):
        return InteractionRelation(
            status="unrelated",
            source="+".join(dict.fromkeys(item.source for item in relations if item.source)),
        )
    return InteractionRelation()


def _structural_scope_ancestry(
    field: Dict[str, Any],
    action: Dict[str, Any],
) -> bool:
    # ``scopeLockable=False`` explicitly means that discovery only found a
    # broad/page-level container. It must not become positive ownership
    # evidence through this compatibility fallback.
    if (
        field.get("scopeLockable") is False
        or action.get("scopeLockable") is False
    ):
        return False
    field_scope = _scope_selector(field)
    action_scope = _scope_selector(action)
    if not field_scope or not action_scope:
        return False
    if not (
        selector_contains(field_scope, action_scope)
        or selector_contains(action_scope, field_scope)
    ):
        return False

    field_role = _scope_role(field)
    action_role = _scope_role(action)
    boundary_role = action_role if selector_contains(action_scope, field_scope) else field_role
    if boundary_role in _MEANINGFUL_BOUNDARY_ROLES:
        return True

    # The same non-page inferred container remains useful positive evidence.
    return field_scope == action_scope and not _is_page_root_scope(field_scope)


def _is_page_root_scope(selector: str) -> bool:
    normalized = " ".join(str(selector or "").strip().lower().split())
    return normalized in {"body", "html", "html > body", ":root", "#app", "#root"}


def _associated_field_selectors(action: Dict[str, Any]) -> set[str]:
    return {
        str(item or "").strip()
        for item in list(action.get("associatedFieldSelectors") or [])
        if str(item or "").strip()
    }


def _selector(target: Dict[str, Any]) -> str:
    return str(target.get("selector") or "").strip()


def _scope_selector(target: Dict[str, Any]) -> str:
    return str(target.get("scopeSelector") or target.get("scope_selector") or "").strip()


def _scope_role(target: Dict[str, Any]) -> str:
    return str(
        target.get("scopeRole")
        or target.get("scope_role")
        or target.get("formOwnerRole")
        or ""
    ).strip().lower()


def _form_owner(target: Dict[str, Any]) -> str:
    return str(target.get("formOwnerSelector") or "").strip()


def _component_owner(target: Dict[str, Any]) -> str:
    return str(target.get("componentOwnerSelector") or "").strip()


def _component_owner_lockable(target: Dict[str, Any]) -> bool:
    return target.get("componentOwnerLockable") is True


def _component_owner_associable(target: Dict[str, Any]) -> bool:
    explicit = target.get("componentOwnerAssociable")
    if explicit is not None:
        return explicit is True and _component_form_count(target) <= 1
    # Observations created before component association was separated from
    # scope locking remain compatible.
    return _component_owner_lockable(target)


def _component_form_count(target: Dict[str, Any]) -> int:
    try:
        return max(0, int(target.get("componentOwnerFormCount") or 0))
    except (TypeError, ValueError):
        return 2


def _component_contains_target(
    component_selector: str,
    target: Dict[str, Any],
) -> bool:
    selector = _form_owner(target) or _selector(target)
    if not selector or selector_contains(component_selector, selector):
        return True

    # A compact selector such as "#answer-form" identifies the target but does
    # not encode its ancestors. Exact shared component-owner metadata remains
    # the stronger relation signal, so a missing path is not a contradiction.
    return " > " not in selector


def _field_association_kind(target: Dict[str, Any]) -> str:
    return str(target.get("fieldAssociationKind") or "").strip().lower()


def _cross_frame_host_component_relation(
    *,
    inner: Dict[str, Any],
    outer: Dict[str, Any],
) -> InteractionRelation:
    """Relate an iframe interaction to an outer control using explicit owners."""
    host_selectors = _frame_host_scope_selectors(inner)
    if not host_selectors:
        return InteractionRelation()

    outer_form = _form_owner(outer)
    if outer_form:
        if any(_selectors_overlap(host, outer_form) for host in host_selectors):
            return InteractionRelation(
                status="related",
                source="frame_host_form_owner",
            )
        return InteractionRelation(
            status="unrelated",
            source="frame_host_form_owner",
        )

    component = _component_owner(outer)
    if (
        not component
        or _is_page_root_scope(component)
        or not _component_contains_target(component, outer)
    ):
        return InteractionRelation()
    if any(selector_contains(component, host) for host in host_selectors):
        return InteractionRelation(
            status="related",
            source="frame_host_component_owner",
        )
    return InteractionRelation()


def _frame_host_scope_selectors(target: Dict[str, Any]) -> tuple[str, ...]:
    raw = (
        target.get("frameHostScopeIds")
        or target.get("frame_host_scope_ids")
        or []
    )
    if not isinstance(raw, (list, tuple)):
        return ()
    selectors = []
    for item in raw:
        scope_id = str(item or "").strip()
        if not scope_id:
            continue
        prefix, separator, selector = scope_id.partition(":")
        selectors.append(
            selector.strip()
            if separator and prefix.isdigit()
            else scope_id
        )
    return tuple(dict.fromkeys(item for item in selectors if item))


def _selectors_overlap(left: str, right: str) -> bool:
    return selector_contains(left, right) or selector_contains(right, left)


def _frame_depth(target: Dict[str, Any]) -> int:
    return int(target.get("frameDepth") or 0)


__all__ = [
    "InteractionRelation",
    "RelationStatus",
    "resolve_action_fields_relation",
    "resolve_field_action_relation",
]
