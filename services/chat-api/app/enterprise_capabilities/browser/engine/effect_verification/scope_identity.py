"""Shared DOM interaction-scope identity helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional


@dataclass(frozen=True)
class ScopeIdentity:
    scope_id: str
    selector: str
    frame_depth: int
    ancestor_scope_ids: tuple[str, ...] = ()


def scope_identity(element: Dict[str, Any]) -> Optional[ScopeIdentity]:
    # New sidecars explicitly mark broad/page-level inferred containers as
    # unsuitable for a hard form lock. Missing metadata remains compatible
    # with older sidecars and stored observations.
    ancestor_scope_ids = _ancestor_scope_ids(element)
    local_scope_lockable = element.get("scopeLockable") is not False
    if not local_scope_lockable and not ancestor_scope_ids:
        return None
    scope_id = (
        str(element.get("scopeId") or "").strip()
        if local_scope_lockable else ""
    )
    selector = (
        str(element.get("scopeSelector") or "").strip()
        if local_scope_lockable else ""
    )
    if not scope_id and not selector and not ancestor_scope_ids:
        return None
    frame_depth = int(element.get("frameDepth") or 0)
    if not scope_id and not selector:
        scope_id = f"{frame_depth}:frame-host:{ancestor_scope_ids[-1]}"
    return ScopeIdentity(
        scope_id=scope_id or f"{frame_depth}:{selector}",
        selector=selector,
        frame_depth=frame_depth,
        ancestor_scope_ids=ancestor_scope_ids,
    )


def scopes_related(left: ScopeIdentity, right: ScopeIdentity) -> bool:
    if left.frame_depth != right.frame_depth:
        left_ancestors = set(left.ancestor_scope_ids)
        right_ancestors = set(right.ancestor_scope_ids)
        return bool(
            left.scope_id in right_ancestors
            or right.scope_id in left_ancestors
            or left_ancestors.intersection(right_ancestors)
        )
    if left.scope_id == right.scope_id:
        return True
    if not left.selector or not right.selector:
        return False
    return selector_contains(left.selector, right.selector) or selector_contains(
        right.selector,
        left.selector,
    )


def scope_present(
    active: ScopeIdentity,
    elements: Iterable[Dict[str, Any]],
) -> bool:
    """Return true only for the active scope itself or its descendants."""
    for item in elements:
        observed = scope_identity(item)
        if observed is None or active.frame_depth != observed.frame_depth:
            continue
        if active.scope_id == observed.scope_id:
            return True
        if active.selector and observed.selector and selector_contains(active.selector, observed.selector):
            return True
    return False


def selector_contains(parent: str, child: str) -> bool:
    return child == parent or child.startswith(parent + " > ")


def _ancestor_scope_ids(element: Dict[str, Any]) -> tuple[str, ...]:
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
    "ScopeIdentity",
    "scope_identity",
    "scope_present",
    "scopes_related",
    "selector_contains",
]
