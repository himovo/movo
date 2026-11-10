"""Decide when a live conversation may defer an additive profile change."""

from __future__ import annotations

from collections import Counter
import json

from .models import RuntimeProfileSnapshot
from .plugin_skill_selection import selection_id
from .plugin_command_selection import selection_id as command_selection_id


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
    selected_command_id: str | None = None,
) -> bool:
    """Keep an existing session only if its full execution contract remains allowed."""
    if selected_skill_id:
        known = {skill.source_id for skill in current.skills}
        for plugin in current.plugins:
            for skill in plugin.get("skills") or []:
                if skill.get("userInvocable") is True:
                    known.add(selection_id(str(plugin["installation_id"]), str(skill["name"])))
        if selected_skill_id not in known:
            return False
    if selected_command_id:
        known_commands = {
            command_selection_id(str(plugin["installation_id"]), str(command["name"]))
            for plugin in current.plugins for command in plugin.get("commands") or []
            if command.get("definitionId")
        }
        if selected_command_id not in known_commands:
            return False
    old = current.execution_payload()
    new = desired.execution_payload()
    for names in _COLLECTIONS:
        for name in names:
            if not _members(old.pop(name)) <= _members(new.pop(name)):
                return False
    return old == new
