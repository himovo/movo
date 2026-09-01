from __future__ import annotations

from typing import Dict, Iterable, List

from app.enterprise_capabilities.browser.engine.action_target import locator_match_score
from app.enterprise_capabilities.browser.engine.form_input.contracts import FieldBinding, FieldDescriptor
from app.enterprise_capabilities.browser.engine.form_input.input_context import BrowserInputContext, InputCandidate

from .contracts import CachedFieldBinding


def resolve_cached_bindings(
    fields: List[FieldDescriptor],
    context: BrowserInputContext,
    hints: Iterable[CachedFieldBinding],
) -> Dict[str, FieldBinding]:
    """Project cached semantic mappings onto current fields and current values."""
    resolved: Dict[str, FieldBinding] = {}
    used_candidates: set[str] = set()
    for hint in hints:
        field = _unique_field(fields, hint)
        candidate = _unique_candidate(context, hint)
        if field is None or candidate is None or candidate.candidate_id in used_candidates:
            continue
        binding = _binding(field, candidate, hint)
        if binding is None:
            continue
        resolved[field.field_key] = binding
        used_candidates.add(candidate.candidate_id)
    return resolved


def _unique_field(fields: List[FieldDescriptor], hint: CachedFieldBinding) -> FieldDescriptor | None:
    scored = sorted(
        (
            (locator_match_score(hint.locator, field.raw), field)
            for field in fields
            if not field.current_value.strip() and not field.sensitive
        ),
        key=lambda item: item[0],
        reverse=True,
    )
    if not scored or scored[0][0] <= 0:
        return None
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None
    return scored[0][1]


def _unique_candidate(context: BrowserInputContext, hint: CachedFieldBinding) -> InputCandidate | None:
    exact = [item for item in context.candidates if hint.source_path and item.source_path == hint.source_path]
    candidates = exact or [
        item for item in context.candidates
        if str(item.semantic_name or "").strip().casefold() == hint.semantic_name.strip().casefold()
    ]
    return candidates[0] if len(candidates) == 1 else None


def _binding(
    field: FieldDescriptor,
    candidate: InputCandidate,
    hint: CachedFieldBinding,
) -> FieldBinding | None:
    if hint.action == "upload":
        if field.control_kind != "file" or candidate.value_kind != "file":
            return None
        value = (
            list(candidate.value)
            if isinstance(candidate.value, list)
            else [str(candidate.value)] if str(candidate.value or "").strip() else []
        )
        if not value:
            return None
        source_kind = "attachment"
    else:
        if field.control_kind == "file" or candidate.value_kind == "file":
            return None
        value = str(candidate.value or "")
        if not value:
            return None
        if hint.action == "select":
            matching = [item for item in field.options if item.strip().casefold() == value.strip().casefold()]
            if len(matching) != 1:
                return None
            value = matching[0]
        source_kind = "selection" if hint.action == "select" else (
            "user_input" if candidate.source_kind == "user_input" else "upstream"
        )
    return FieldBinding(
        field_key=field.field_key,
        action=hint.action,
        source_kind=source_kind,
        value=value,
        candidate_id=candidate.candidate_id,
        source_path=candidate.source_path,
        plain_text=candidate.plain_text,
        rich_html=candidate.rich_html,
        confidence=0.99,
        rationale="旁路缓存复用了已验证的字段语义映射",
    )


__all__ = ["resolve_cached_bindings"]
