from __future__ import annotations

from typing import Any

from app.enterprise_capabilities.runtime.contracts import CapabilityExecutionContext
from app.services.skillhub import SkillHubError, SkillHubInstallService


async def skillhub_install(
    arguments: dict[str, Any], context: CapabilityExecutionContext,
) -> dict[str, Any]:
    """Install into the trusted caller's personal Skill collection."""
    try:
        return await SkillHubInstallService().install_personal(
            coordinate=str(arguments.get("coordinate") or ""),
            version=str(arguments.get("version") or ""),
            tenant_id=context.tenant_id,
            user_id=context.user_id,
        )
    except SkillHubError as exc:
        return exc.result()
