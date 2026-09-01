"""Shared ASKAI admission for every server-side DSH turn."""

from __future__ import annotations

from dataclasses import dataclass

from app.dsh_runtime.profile.skills import MongoSkillCatalog
from app.dsh_runtime.profile.skills.resolver import require_selected_skill
from app.governance.audit import record_position_policy_event
from app.governance.position_policy import MongoEmployeePolicyResolver


@dataclass(frozen=True)
class TurnSkillSelection:
    selected_skill_id: str | None = None
    selected_writing_skill_id: str | None = None


async def admit_skill_selection(
    *, tenant_id: str, user_id: str, selected_skill_id: str | None
) -> TurnSkillSelection:
    """Authorize one opaque control-plane Skill id before Profile execution."""

    selected = str(selected_skill_id or "").strip()
    if not selected:
        return TurnSkillSelection()
    policy = await MongoEmployeePolicyResolver().resolve(tenant_id, user_id)
    if not policy.allows_skill(selected):
        await record_position_policy_event(
            tenant_id=tenant_id,
            user_id=user_id,
            action="capability.denied",
            target="skill",
            details={"skill_id": selected},
        )
        raise PermissionError("当前岗位未开通该 Skill")
    kind, _row = await require_selected_skill(
        MongoSkillCatalog(MongoEmployeePolicyResolver()),
        skill_id=selected,
        tenant_id=tenant_id,
        user_id=user_id,
    )
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
