"""Stable resource identity for repeated business-form transactions.

The same SPA form DOM is often reused for several records (comments, reviews,
approvals).  Form state must therefore be scoped to the record being edited,
not just to the form selector.  Identity resolution is deliberately
conservative: a changing URL resource or strong DOM content identity starts a
new transaction; weak/temporarily missing evidence never does.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional

from app.enterprise_capabilities.browser.engine.business_action import browser_target_identity
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation

from .contracts import FieldDescriptor


@dataclass(frozen=True)
class FormResourceIdentity:
    key: str
    source: str
    url_resource: str = ""
    evidence: str = ""

    def as_dict(self) -> Dict[str, str]:
        return {
            "key": self.key,
            "source": self.source,
            "url_resource": self.url_resource,
            "evidence": self.evidence,
        }

    @classmethod
    def from_dict(cls, value: Any) -> Optional["FormResourceIdentity"]:
        if not isinstance(value, dict) or not str(value.get("key") or "").strip():
            return None
        return cls(
            key=str(value.get("key") or "").strip(),
            source=str(value.get("source") or "fallback").strip(),
            url_resource=str(value.get("url_resource") or "").strip(),
            evidence=str(value.get("evidence") or "").strip(),
        )


@dataclass(frozen=True)
class FormResourceTransition:
    identity: FormResourceIdentity
    changed: bool = False
    upgraded: bool = False


class FormResourceIdentityTracker:
    """Keep strong identity across transient observations and detect changes."""

    def __init__(self) -> None:
        self._active: Optional[FormResourceIdentity] = None

    @property
    def active(self) -> Optional[FormResourceIdentity]:
        return self._active

    def observe(
        self,
        candidate: FormResourceIdentity,
        *,
        allow_change: bool = True,
    ) -> FormResourceTransition:
        active = self._active
        if active is None:
            self._active = candidate
            return FormResourceTransition(candidate)
        if active.key == candidate.key:
            return FormResourceTransition(active)

        # A strong DOM identity can temporarily disappear during SPA rerenders.
        # Do not downgrade and accidentally open a second submission window.
        if active.source == "dom" and candidate.source != "dom":
            if not _different_url_resource(active, candidate):
                return FormResourceTransition(active)

        # DOM metadata may arrive one observation after the form. Treat this as
        # an identity upgrade, not a record change, when the URL resource agrees.
        if active.source != "dom" and candidate.source == "dom":
            if not _different_url_resource(active, candidate):
                self._active = candidate
                return FormResourceTransition(candidate, upgraded=True)

        # A form can become observable before a SPA finishes assigning its
        # resource URL. Adopt the later URL without discarding form progress.
        if active.source == "fallback" and candidate.source == "url":
            self._active = candidate
            return FormResourceTransition(candidate, upgraded=True)

        # With no strong resource evidence, preserve the current transaction.
        # This is safer than allowing a duplicate external submission.
        if active.source == "fallback" or candidate.source == "fallback":
            return FormResourceTransition(active)

        if not allow_change:
            return FormResourceTransition(active)

        self._active = candidate
        return FormResourceTransition(candidate, changed=True)

    def export_state(self) -> Dict[str, str]:
        return self._active.as_dict() if self._active is not None else {}

    def restore_state(self, value: Any) -> None:
        self._active = FormResourceIdentity.from_dict(value)


@dataclass
class FormTransactionMemory:
    completed_keys: set[str] = field(default_factory=set)
    mutated_field_keys: set[str] = field(default_factory=set)
    blocked_keys: set[str] = field(default_factory=set)
    skipped_keys: set[str] = field(default_factory=set)
    commit_attempts: set[str] = field(default_factory=set)
    commit_unresolved_counts: Dict[str, int] = field(default_factory=dict)


def resolve_form_resource_identity(
    observation: Observation,
    fields: Iterable[FieldDescriptor],
) -> FormResourceIdentity:
    field_list = list(fields)
    system_id, url_resource = browser_target_identity(observation.url)
    dom_identity, dom_source = _dom_content_identity(field_list)
    if dom_identity:
        return FormResourceIdentity(
            key=f"{system_id or 'unknown'}\0dom\0{dom_identity}",
            source="dom",
            url_resource=url_resource,
            evidence=dom_source,
        )
    if url_resource:
        return FormResourceIdentity(
            key=f"{system_id or 'unknown'}\0url\0{url_resource}",
            source="url",
            url_resource=url_resource,
            evidence=url_resource,
        )
    return FormResourceIdentity(
        key=f"{system_id or 'unknown'}\0unresolved",
        source="fallback",
        url_resource="",
        evidence="no stable URL or DOM content identity",
    )


def _dom_content_identity(fields: Iterable[FieldDescriptor]) -> tuple[str, str]:
    values: Dict[str, int] = {}
    sources: Dict[str, str] = {}
    for field in fields:
        raw = field.raw
        value = str(
            raw.get("contentContextId")
            or raw.get("content_context_id")
            or ""
        ).strip()
        if not value:
            continue
        values[value] = values.get(value, 0) + 1
        sources[value] = str(
            raw.get("contentContextSource")
            or raw.get("content_context_source")
            or "dom"
        ).strip()
    if not values:
        return "", ""
    # All fields in a form normally share the same context. In a mixed surface,
    # only accept a unique majority so an incidental field cannot rotate state.
    ranked = sorted(values.items(), key=lambda item: (-item[1], item[0]))
    winner, count = ranked[0]
    if len(ranked) > 1 and count == ranked[1][1]:
        return "", ""
    return winner[:320], sources.get(winner, "dom")[:80]


def _different_url_resource(
    left: FormResourceIdentity,
    right: FormResourceIdentity,
) -> bool:
    return bool(
        left.url_resource
        and right.url_resource
        and left.url_resource != right.url_resource
    )


__all__ = [
    "FormResourceIdentity",
    "FormResourceIdentityTracker",
    "FormResourceTransition",
    "FormTransactionMemory",
    "resolve_form_resource_identity",
]
