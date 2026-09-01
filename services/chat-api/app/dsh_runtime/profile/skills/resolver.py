"""Resolve a manually selected, policy-authorized Skill at the API boundary."""

from __future__ import annotations

from typing import Any, Literal

from app.enterprise_capabilities.content.styles import is_writing_style

from .catalog import SkillCatalog


async def require_selected_skill(
    catalog: SkillCatalog,
    *,
    skill_id: str,
    tenant_id: str,
    user_id: str,
) -> tuple[Literal["writing_style", "skill"], dict[str, Any]]:
    selected = next(
        (item for item in await catalog.list_enabled(tenant_id, user_id) if str(item.get("id") or "") == skill_id),
        None,
    )
    if selected is None:
        raise LookupError("选择的 Skill 不存在、已停用或当前岗位不可用")
    return ("writing_style" if is_writing_style(selected) else "skill"), selected
