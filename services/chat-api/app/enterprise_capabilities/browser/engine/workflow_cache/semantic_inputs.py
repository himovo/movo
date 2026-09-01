from __future__ import annotations

import hashlib
from typing import Iterable

from pydantic import BaseModel, Field

from app.enterprise_capabilities.browser.engine.form_input.input_context import BrowserInputContext, InputCandidate


class SemanticInputValue(BaseModel):
    """One explicit business value extracted from the current request."""

    role: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=20000)


def add_semantic_request_inputs(
    context: BrowserInputContext,
    values: Iterable[SemanticInputValue],
    *,
    allowed_roles: Iterable[str],
) -> list[str]:
    """Add model-extracted request values after strict local validation.

    The model chooses the semantic mapping, while local code ensures that it
    cannot invent a value or a role the selected workflow never requested.
    """
    request = str(context.original_request or "")
    allowed = {_role(item) for item in allowed_roles if _role(item)}
    existing = {
        (_role(item.semantic_name), str(item.value or ""))
        for item in context.candidates
    }
    added: list[str] = []
    for item in values:
        role = _role(item.role)
        value = str(item.value or "").strip()
        if not role or role not in allowed or not value or value not in request:
            continue
        if (role, value) in existing:
            continue
        digest = hashlib.sha256(f"{role}\0{value}".encode("utf-8")).hexdigest()[:20]
        context.candidates.append(InputCandidate(
            candidate_id=f"request-semantic-{digest}",
            source_kind="request_semantic",
            source_path=f"request_semantic.{role}",
            semantic_name=role,
            value=value,
            value_kind="text",
            plain_text=value,
            metadata={"binding_authority": "request_semantic"},
        ))
        existing.add((role, value))
        added.append(role)
    return added


def _role(value: object) -> str:
    return str(value or "").strip().casefold()


__all__ = ["SemanticInputValue", "add_semantic_request_inputs"]
