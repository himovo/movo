"""Verify that a selected result exposed its own inline editor.

Some result lists support replying or commenting without navigating to a
separate detail URL. This is an alternative form of opening the selected
business object, but only when the newly exposed editor is structurally owned
by the clicked result. Unrelated search, authentication, and page-level
editors must not satisfy detail progress.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

from app.enterprise_capabilities.browser.engine.auth_state import BLOCKING_STATES
from app.enterprise_capabilities.browser.engine.effect_verification.decision_target import (
    resolve_effect_target,
)
from app.enterprise_capabilities.browser.engine.effect_verification.interaction_relation import (
    resolve_field_action_relation,
)
from app.enterprise_capabilities.browser.engine.effect_verification.interaction_transition import (
    detect_interaction_transition,
)
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation

from .detail_progress import DetailTargetFingerprint, same_detail_resource


_EDITABLE_ROLES = {"textbox", "searchbox", "combobox", "spinbutton"}


@dataclass(frozen=True)
class InlineTargetEditorEvidence:
    confirmed: bool = False
    field_ref: str = ""
    relation_source: str = ""
    reason: str = ""


def inline_target_editor_observed(
    decision: Decision,
    before: Observation,
    after: Observation,
    *,
    target: Optional[DetailTargetFingerprint],
) -> InlineTargetEditorEvidence:
    """Return positive evidence for a target-owned same-page editor."""
    if decision.tool not in {"browser_click", "browser_click_at"}:
        return InlineTargetEditorEvidence(reason="unsupported_action")
    if target is None or not before.fresh or not after.fresh:
        return InlineTargetEditorEvidence(reason="missing_fresh_target_context")
    if not same_detail_resource(before.url, after.url):
        return InlineTargetEditorEvidence(reason="page_resource_changed")
    if _auth_is_blocking(after):
        return InlineTargetEditorEvidence(reason="authentication_surface")

    action = resolve_effect_target(decision, before)
    if not action or _is_editable(action) or _is_search_field(action):
        return InlineTargetEditorEvidence(reason="invalid_action_target")

    interaction = detect_interaction_transition(before=before, after=after)
    if interaction is None or interaction.kind != "editor_opened":
        return InlineTargetEditorEvidence(reason="no_editor_transition")

    for field in _new_editable_fields(before.elements, after.elements):
        if _is_search_field(field) or _is_auth_field(field):
            continue
        relation = resolve_field_action_relation(field, action)
        if relation.related:
            return InlineTargetEditorEvidence(
                confirmed=True,
                field_ref=str(field.get("ref") or ""),
                relation_source=relation.source,
                reason=interaction.reason,
            )
    return InlineTargetEditorEvidence(reason="editor_not_owned_by_target")


def _new_editable_fields(
    before: Iterable[Dict[str, Any]],
    after: Iterable[Dict[str, Any]],
) -> list[Dict[str, Any]]:
    before_fields = {
        _field_identity(item)
        for item in before
        if isinstance(item, dict) and _is_editable(item)
    }
    return [
        item
        for item in after
        if isinstance(item, dict)
        and _is_editable(item)
        and _field_identity(item) not in before_fields
    ]


def _field_identity(item: Dict[str, Any]) -> str:
    selector = str(item.get("selector") or "").strip()
    frame_depth = str(item.get("frameDepth") or 0)
    if selector:
        return f"{frame_depth}:selector:{selector}"
    return "\x00".join(
        str(item.get(key) or "").strip().casefold()
        for key in (
            "frameDepth",
            "role",
            "name",
            "placeholder",
            "type",
            "description",
            "scopeId",
            "scopeSelector",
        )
    )


def _is_editable(item: Dict[str, Any]) -> bool:
    return (
        item.get("disabled") is not True
        and item.get("visible") is not False
        and (
            item.get("editable") is True
            or str(item.get("role") or "").strip().casefold() in _EDITABLE_ROLES
        )
    )


def _is_search_field(item: Dict[str, Any]) -> bool:
    return (
        str(item.get("semanticPurpose") or "").strip().casefold() == "search"
        or bool(item.get("searchContext"))
        or str(item.get("role") or "").strip().casefold() == "searchbox"
        or str(item.get("scopeRole") or "").strip().casefold() == "search"
    )


def _is_auth_field(item: Dict[str, Any]) -> bool:
    input_type = str(item.get("type") or "").strip().casefold()
    autocomplete = str(item.get("autocomplete") or "").strip().casefold()
    return input_type == "password" or autocomplete in {
        "current-password",
        "new-password",
        "one-time-code",
    }


def _auth_is_blocking(observation: Observation) -> bool:
    auth = observation.auth if isinstance(observation.auth, dict) else {}
    return str(auth.get("state") or "").strip().casefold() in BLOCKING_STATES


__all__ = [
    "InlineTargetEditorEvidence",
    "inline_target_editor_observed",
]
