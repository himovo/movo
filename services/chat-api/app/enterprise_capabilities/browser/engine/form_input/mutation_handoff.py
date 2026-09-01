"""Adopt verified form mutations performed by the fallback browser planner."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation

from .identity import visible_text
from .inventory import discover_fields
from .readiness import ready_business_form_scopes


@dataclass(frozen=True)
class FormMutationHandoff:
    field_key: str
    scope_id: str


def resolve_fallback_form_mutation(
    *,
    decision: Decision,
    before: Observation | None,
    after: Observation,
) -> Optional[FormMutationHandoff]:
    """Return a handoff only for a live, verified business-form fill.

    The executor has already applied a confirmed fill receipt to ``after``.
    Requiring the expected value in that observation prevents an LLM-planned
    stale or failed fill from entering the deterministic commit transaction.
    """
    if before is None or decision.tool != "browser_fill":
        return None
    args = decision.args or {}
    ref = str(args.get("ref") or "").strip()
    expected = visible_text(args.get("value"))
    if not ref or not expected:
        return None

    before_fields = discover_fields(before)
    before_field = next((field for field in before_fields if field.ref == ref), None)
    if before_field is None or before_field.sensitive:
        return None
    ready_before = ready_business_form_scopes(before, before_fields)
    if before_field.scope_id not in ready_before:
        return None

    after_fields = {field.field_key: field for field in discover_fields(after)}
    after_field = after_fields.get(before_field.field_key)
    if after_field is None or after_field.sensitive:
        return None
    if visible_text(after_field.current_value) != expected:
        return None

    return FormMutationHandoff(
        field_key=before_field.field_key,
        scope_id=before_field.scope_id,
    )


__all__ = ["FormMutationHandoff", "resolve_fallback_form_mutation"]
