"""Resolve a form's commit control after its fields have been filled."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Literal, Optional

from app.enterprise_capabilities.browser.engine.effect_verification.interaction_relation import (
    InteractionRelation,
    resolve_action_fields_relation,
)
from app.enterprise_capabilities.browser.engine.rules.tokens.form import COMMIT_ACTION, NON_COMMIT_ACTION
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation

from .commit_binding import commit_control_key
from .contracts import FieldDescriptor


ResolutionKind = Literal["click", "refresh", "ambiguous", "none"]
_ACTION_ROLES = {"button", "menuitem"}
_STATUS_PREFIXES = ("已", "already ", "sent", "published", "submitted", "saved")


@dataclass(frozen=True)
class CommitResolution:
    kind: ResolutionKind
    decision: Optional[Decision] = None
    candidate_refs: tuple[str, ...] = ()
    reason: str = ""


def resolve_form_commit(
    observation: Observation,
    *,
    fields: Iterable[FieldDescriptor],
    mutated_field_keys: Iterable[str],
    observation_is_fresh: bool,
    bound_action_keys: Iterable[str] = (),
) -> CommitResolution:
    """Return a deterministic commit only when one live candidate is clear."""
    field_list = list(fields)
    mutated = set(mutated_field_keys)
    owned_fields = [field for field in field_list if field.field_key in mutated]
    if not owned_fields:
        return CommitResolution(kind="none", reason="no field changed by this transaction")
    if not any(field.current_value.strip() for field in owned_fields):
        return CommitResolution(kind="none", reason="changed field value is not present in current DOM")
    if any(field.required and not field.current_value.strip() for field in field_list):
        return CommitResolution(kind="none", reason="required fields remain empty")

    candidates = _related_candidates(
        observation.elements or [],
        owned_fields,
        bound_action_keys=set(bound_action_keys),
    )
    enabled = [item for item in candidates if not item.get("disabled")]
    if candidates and not observation_is_fresh:
        refs = tuple(str(item.get("ref") or "") for item in candidates)
        return CommitResolution(
            kind="refresh",
            decision=Decision(
                tool="browser_observe",
                args={},
                rationale="[form_commit_resolver] refresh after fill before resolving commit control",
            ),
            candidate_refs=refs,
            reason="commit controls must be resolved from a post-fill observation",
        )
    if len(enabled) == 1:
        ref = str(enabled[0].get("ref") or "").strip()
        return CommitResolution(
            kind="click",
            decision=Decision(
                tool="browser_click",
                args={"ref": ref},
                rationale="[form_commit_resolver] unique enabled commit control in active form",
            ),
            candidate_refs=(ref,),
            reason="unique enabled commit control",
        )
    refs = tuple(str(item.get("ref") or "") for item in (enabled or candidates))
    if candidates:
        return CommitResolution(
            kind="ambiguous",
            candidate_refs=refs,
            reason="multiple commit controls require planner selection" if enabled else "commit controls remain disabled",
        )
    return CommitResolution(kind="none", reason="no semantic commit control in active form")


def _related_candidates(
    elements: Iterable[Any],
    fields: List[FieldDescriptor],
    *,
    bound_action_keys: set[str],
) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for item in elements:
        if not isinstance(item, dict):
            continue
        if not is_semantic_commit_control(
            item,
            require_hit_testable=not bool(item.get("disabled")),
        ):
            continue
        relation = commit_control_relation_for_fields(
            item,
            fields=fields,
            require_hit_testable=False,
        )
        if (
            relation.related
            or commit_control_key(item) in bound_action_keys
        ):
            candidates.append(item)
    return candidates


def is_commit_control_for_fields(
    element: Dict[str, Any],
    *,
    fields: Iterable[FieldDescriptor],
    require_hit_testable: bool = True,
) -> bool:
    """Return whether a commit control belongs to the supplied form fields."""
    return commit_control_relation_for_fields(
        element,
        fields=fields,
        require_hit_testable=require_hit_testable,
    ).related


def commit_control_relation_for_fields(
    element: Dict[str, Any],
    *,
    fields: Iterable[FieldDescriptor],
    require_hit_testable: bool = True,
) -> InteractionRelation:
    """Return the canonical three-state relationship for a commit control."""
    if not is_semantic_commit_control(
        element,
        require_hit_testable=require_hit_testable,
    ):
        return InteractionRelation()
    return resolve_action_fields_relation(
        action=element,
        fields=(field.raw for field in fields),
    )


def is_semantic_commit_control(
    element: Dict[str, Any],
    *,
    require_hit_testable: bool = True,
) -> bool:
    """Return whether an element semantically represents a form commit.

    Disabled controls intentionally remain recognizable. Readiness uses that
    structural signal before a field is filled, while ``resolve_form_commit``
    separately requires the selected candidate to be enabled.
    """
    if element.get("visible") is False:
        return False
    if require_hit_testable and element.get("hitTestable") is False:
        return False
    role = str(element.get("role") or "").strip().casefold()
    element_type = str(element.get("type") or "").strip().casefold()
    if role not in _ACTION_ROLES and element_type not in {"submit", "button"}:
        return False
    label = _normalize_label(" ".join(
        str(element.get(key) or "") for key in ("name", "text", "value")
    ))
    if element_type == "submit" and not _is_non_commit_label(label):
        return True
    if not label or _is_non_commit_label(label) or label.startswith(_STATUS_PREFIXES):
        return False
    return any(_contains_action(label, token) for token in COMMIT_ACTION)


def _normalize_label(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def _is_non_commit_label(label: str) -> bool:
    return any(_contains_action(label, token) for token in NON_COMMIT_ACTION)


def _contains_action(label: str, token: str) -> bool:
    normalized = str(token or "").casefold()
    if not normalized:
        return False
    if normalized.isascii():
        return bool(re.search(rf"(?<![a-z0-9_]){re.escape(normalized)}(?![a-z0-9_])", label))
    return normalized in label


__all__ = [
    "CommitResolution",
    "commit_control_relation_for_fields",
    "is_commit_control_for_fields",
    "is_semantic_commit_control",
    "resolve_form_commit",
]
