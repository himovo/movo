"""Recovery policy for media that belongs to a replaced rich-text body."""
from __future__ import annotations

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision

from .contracts import FieldDescriptor


def replacement_invalidates_editor_media(
    field: FieldDescriptor | None,
    decision: Decision,
) -> bool:
    """Return true only for replacement writes to the article/message body."""

    return bool(
        field is not None
        and field.semantic_role == "body"
        and decision.tool == "browser_fill"
    )


__all__ = ["replacement_invalidates_editor_media"]
