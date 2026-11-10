"""Shared ASKAI admission for every server-side DSH turn."""

from __future__ import annotations

from dataclasses import dataclass

from app.dsh_runtime.profile.skills import MongoSkillCatalog
from app.dsh_runtime.profile.skills.resolver import require_selected_skill
from app.governance.audit import record_position_policy_event
from app.product.resource_access import resource_is_allowed
from app.dsh_runtime.profile.skills.execution_access import skill_execution_is_allowed
from app.dsh_runtime.profile.plugin_skill_selection import PREFIX as PLUGIN_SKILL_PREFIX, require_plugin_skill
from app.dsh_runtime.profile.plugin_command_selection import PREFIX as PLUGIN_COMMAND_PREFIX, require_plugin_command


@dataclass(frozen=True)
class TurnSkillSelection:
    selected_skill_id: str | None = None
    selected_writing_skill_id: str | None = None
    selected_command_id: str | None = None


async def admit_skill_selection(
    *, tenant_id: str, user_id: str, selected_skill_id: str | None
) -> TurnSkillSelection:
    """Authorize one opaque control-plane Skill id before Profile execution."""

    selected = str(selected_skill_id or "").strip()
    if not selected:
        return TurnSkillSelection()
    if selected.startswith(PLUGIN_COMMAND_PREFIX):
        await require_plugin_command(tenant_id=tenant_id, user_id=user_id, selected_id=selected)
        await record_position_policy_event(
            tenant_id=tenant_id, user_id=user_id,
            action="capability.used", target="plugin_command",
            details={"command_id": selected},
        )
        return TurnSkillSelection(selected_command_id=selected)
    if selected.startswith(PLUGIN_SKILL_PREFIX):
        await require_plugin_skill(tenant_id=tenant_id, user_id=user_id, selected_id=selected)
        await record_position_policy_event(
            tenant_id=tenant_id, user_id=user_id,
            action="capability.used", target="plugin_skill",
            details={"skill_id": selected},
        )
        return TurnSkillSelection(selected_skill_id=selected)
    if not await resource_is_allowed(
        "skill", main_id=tenant_id, user_id=user_id, resource_id=selected.removeprefix("org_skill:")
    ):
        await record_position_policy_event(
            tenant_id=tenant_id,
            user_id=user_id,
            action="capability.denied",
            target="skill",
            details={"skill_id": selected},
        )
        raise PermissionError("该 Skill 未向当前用户开放")
    kind, row = await require_selected_skill(
        MongoSkillCatalog(),
        skill_id=selected,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    if kind == "skill" and not await skill_execution_is_allowed(
        row=row, tenant_id=tenant_id, user_id=user_id,
    ):
        raise PermissionError("Selected Skill requires an execution capability unavailable to this user")
    await record_position_policy_event(
        tenant_id=tenant_id,
        user_id=user_id,
        action="capability.used",
        target="skill",
        details={"skill_id": selected},
    )
    if kind == "writing_style":
        return TurnSkillSelection(selected_writing_skill_id=selected)
    return TurnSkillSelection(selected_skill_id=selected)
