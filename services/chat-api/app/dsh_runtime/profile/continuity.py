"""Decide when a live conversation may defer an additive profile change."""

from __future__ import annotations

from collections import Counter
import json

from .models import RuntimeProfileSnapshot


_COLLECTIONS = (
    ("tools", "tool_versions"),
    ("skills", "skill_versions"),
    ("writing_styles",),
    ("plugins", "plugin_versions"),
)


def _members(values: list[object]) -> Counter[str]:
    return Counter(json.dumps(value, ensure_ascii=False, sort_keys=True) for value in values)


def can_defer_profile_change(
    current: RuntimeProfileSnapshot,
    desired: RuntimeProfileSnapshot,
    *,
    selected_skill_id: str | None = None,
) -> bool:
    """Keep an existing session only if its full execution contract remains allowed."""
    if selected_skill_id and selected_skill_id not in {skill.source_id for skill in current.skills}:
        return False
    old = current.execution_payload()
    new = desired.execution_payload()
    for names in _COLLECTIONS:
        for name in names:
            if not _members(old.pop(name)) <= _members(new.pop(name)):
                return False
    return old == new
