from __future__ import annotations

from typing import Any

from app.enterprise_capabilities.content.style_contract_renderer import build_writer_style_contract
from app.services.org_skill_adapter import organization_skill_adapter
from app.services.skills import user_skill_service


def is_writing_style(skill: dict[str, Any]) -> bool:
    return (
        str(skill.get("type") or "").strip().lower() == "writing_style"
        or str(skill.get("skill_type") or "").strip().lower() == "style"
        or str(skill.get("role") or "").strip().lower() == "style"
    )


async def _available_skills(*, tenant_id: str, user_id: str) -> list[dict[str, Any]]:
    try:
        personal = await user_skill_service.list_skills(user_id, main_id=tenant_id)
    except Exception:
        personal = []
    try:
        organization = await organization_skill_adapter.list_runtime_skills(main_id=tenant_id)
    except Exception:
        organization = []
    return [dict(item) for item in list(personal or []) + list(organization or []) if isinstance(item, dict)]


async def require_writing_style(*, skill_id: str, tenant_id: str, user_id: str) -> dict[str, Any]:
    selected = next(
        (item for item in await _available_skills(tenant_id=tenant_id, user_id=user_id)
         if str(item.get("id") or "").strip() == str(skill_id or "").strip()),
        None,
    )
    if not selected:
        raise LookupError("选择的 Skill 不存在或当前空间不可用")
    if selected.get("enabled", selected.get("is_active", True)) is False:
        raise ValueError("选择的 Skill 已停用")
    if not is_writing_style(selected):
        raise TypeError("工作流 Skill 将在 DSH Skill 迁移步骤接入；当前仅支持内容生产所需的写作规范 Skill")
    return selected


class WritingStyleResolver:
    async def resolve(
        self,
        *,
        request: str,
        tenant_id: str,
        user_id: str,
        selected_skill_id: str = "",
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        if selected_skill_id:
            selected = [await require_writing_style(
                skill_id=selected_skill_id, tenant_id=tenant_id, user_id=user_id,
            )]
        contract = build_writer_style_contract(selected, user_request=request) if selected else {}
        return selected, contract
