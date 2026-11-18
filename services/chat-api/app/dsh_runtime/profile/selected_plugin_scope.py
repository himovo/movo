"""Authorize explicit plugin invocations before choosing a Runtime profile."""

from .plugin_skill_selection import PREFIX as SKILL_PREFIX, require_plugin_skill
from .plugin_command_selection import PREFIX as COMMAND_PREFIX, require_plugin_command


async def selected_plugin_scope(tenant_id, user_id, skill_id=None, command_id=None):
    if command_id and command_id.startswith(COMMAND_PREFIX):
        plugin, _ = await require_plugin_command(
            tenant_id=tenant_id, user_id=user_id, selected_id=command_id,
        )
        return {"selected_plugin_id": plugin["installation_id"]}
    if skill_id and skill_id.startswith(SKILL_PREFIX):
        plugin, _ = await require_plugin_skill(
            tenant_id=tenant_id, user_id=user_id, selected_id=skill_id,
        )
        return {"selected_plugin_id": plugin["installation_id"]}
    return {}
