"""Form-field phase helpers shared by text entry and media insertion."""
from __future__ import annotations

from typing import Any, Dict, Iterable, Sequence

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision

from .contracts import FieldDescriptor
from .field_semantics import semantic_field_role, text_mentions_field_role
from .input_context import BrowserInputContext


_MEDIA_MUTATION_TOOLS = {
    "browser_paste_image",
    "browser_upload_file",
}


def pending_input_fields(
    fields: Sequence[FieldDescriptor],
    *,
    completed_keys: Iterable[str],
    skipped_keys: Iterable[str],
) -> list[FieldDescriptor]:
    """Return live, empty non-media fields not yet resolved by this transaction."""

    completed = {str(item) for item in completed_keys if str(item)}
    skipped = {str(item) for item in skipped_keys if str(item)}
    return [
        field
        for field in fields
        if field.control_kind not in {"file", "toggle"}
        and not field.sensitive
        and not field.current_value.strip()
        and field.field_key not in completed
        and field.field_key not in skipped
    ]


def augment_pending_field_ledger(
    state_ledger: Dict[str, Any] | None,
    fields: Sequence[FieldDescriptor],
) -> Dict[str, Any]:
    """Tell the existing Agent Loop which fields must precede media mutation."""

    ledger = dict(state_ledger or {})
    ledger["form_input_phase"] = "fields_before_media"
    ledger["pending_form_fields"] = [
        {
            "field_key": field.field_key,
            "ref": field.ref,
            "label": field.semantic_label,
            "control_kind": field.control_kind,
            "required": field.required,
            "scope_id": field.scope_id,
        }
        for field in fields[:20]
    ]
    ledger["pending_form_field_count"] = len(fields)
    return ledger


def is_direct_media_mutation(decision: Decision) -> bool:
    return decision.tool in _MEDIA_MUTATION_TOOLS


def skip_resolves_input_phase(
    field: FieldDescriptor,
    *,
    context: BrowserInputContext,
    task_goal: str,
) -> bool:
    """Tell whether a model skip may permanently resolve this live field."""

    if field.required:
        return False
    role = field.semantic_role
    if role not in {"title", "body"}:
        return True
    if text_mentions_field_role(task_goal, role):
        return False
    if text_mentions_field_role(context.original_request, role):
        return False
    return not any(
        candidate.value_kind != "file"
        and semantic_field_role(name=candidate.semantic_name) == role
        for candidate in context.candidates
    )


__all__ = [
    "augment_pending_field_ledger",
    "is_direct_media_mutation",
    "pending_input_fields",
    "skip_resolves_input_phase",
]
