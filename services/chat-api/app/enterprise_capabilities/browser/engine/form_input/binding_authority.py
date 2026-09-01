"""Authority rules for structured publish inputs.

The publish payload is the canonical handoff from an upstream generation
node. Browser exploration may discover where to place that payload, but it
must not rewrite the body or serialize structured media back into text.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Iterable, Mapping, Optional, Sequence

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision

from .contracts import FieldBinding, FieldDescriptor

if TYPE_CHECKING:
    from .input_context import BrowserInputContext, InputCandidate


PUBLISH_AUTHORITY = "publish_payload"
_AUTHORITATIVE_ROLES = {"title", "body"}
_MEDIA_MARKUP_RE = re.compile(
    r"(?:<\s*img\b|&lt;\s*img\b|!\[[^\]]*]\([^)]+\))",
    re.IGNORECASE,
)


def authoritative_publish_candidate(
    field: FieldDescriptor,
    candidates: Iterable[InputCandidate],
) -> Optional[InputCandidate]:
    """Return the unique canonical publish candidate for this field."""
    role = field.semantic_role
    if role not in _AUTHORITATIVE_ROLES:
        return None
    matched = [
        candidate
        for candidate in candidates
        if candidate.metadata.get("binding_authority") == PUBLISH_AUTHORITY
        and candidate.metadata.get("field_role") == role
        and candidate.value_kind != "file"
    ]
    return matched[0] if len(matched) == 1 else None


def direct_authoritative_binding(
    *,
    field: FieldDescriptor,
    candidate: InputCandidate,
    confidence: float,
    rationale: str,
) -> FieldBinding:
    return FieldBinding(
        field_key=field.field_key,
        action="fill",
        source_kind=(
            "user_input"
            if candidate.source_kind == "user_input"
            else "upstream"
        ),
        value=str(candidate.value or ""),
        candidate_id=candidate.candidate_id,
        source_path=candidate.source_path,
        plain_text=candidate.plain_text,
        rich_html=candidate.rich_html,
        confidence=confidence,
        rationale=rationale,
    )


def contains_serialized_media(value: object) -> bool:
    return bool(_MEDIA_MARKUP_RE.search(str(value or "")))


def has_structured_media(candidates: Iterable[InputCandidate]) -> bool:
    return any(candidate.value_kind == "file" for candidate in candidates)


def normalize_authoritative_fill(
    *,
    decision: Decision,
    fields: Sequence[FieldDescriptor],
    context: BrowserInputContext,
) -> Decision:
    """Keep final fill dispatches aligned with the canonical publish payload."""
    if decision.tool != "browser_fill":
        return decision
    ref = str((decision.args or {}).get("ref") or "").strip()
    field = next((item for item in fields if item.ref == ref), None)
    if field is None:
        return decision
    candidate = authoritative_publish_candidate(field, context.candidates)
    if candidate is None:
        return decision

    args = dict(decision.args or {})
    canonical_value = str(candidate.plain_text or candidate.value or "")
    args["value"] = canonical_value
    if field.control_kind == "rich_text" and candidate.rich_html:
        content_editable_mode = str(
            field.raw.get("contentEditableMode")
            or field.raw.get("content_editable_mode")
            or ""
        ).strip().lower()
        if content_editable_mode != "plaintext-only":
            args["rich_html"] = candidate.rich_html
    else:
        args.pop("rich_html", None)
    if args == dict(decision.args or {}):
        return decision
    return Decision(
        tool=decision.tool,
        args=args,
        rationale=(
            f"{decision.rationale} [publish_payload_authority] "
            "use canonical structured content"
        ).strip(),
    )


def authority_metadata(role: str) -> Mapping[str, str]:
    return {
        "binding_authority": PUBLISH_AUTHORITY,
        "field_role": role,
    }
