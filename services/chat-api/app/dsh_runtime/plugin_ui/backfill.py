"""Refresh legacy browser capability records before a plugin UI launch."""

from __future__ import annotations

from app.dsh_runtime.plugin_management.current_assessment import (
    assess_existing_installation, running_dsh_version,
)
from app.dsh_runtime.plugin_management.repository import PluginInstallationRepository


async def backfill_browser_capabilities(
    *, tenant_id: str, user_id: str, plugin: dict,
) -> None:
    repository = PluginInstallationRepository()
    owner = user_id if plugin.get("source_scope") == "personal" else ""
    row = await repository.get(
        main_id=tenant_id, user_id=owner,
        plugin_id=plugin["installation_id"],
    )
    if row is None:
        return
    capabilities = (row.get("availability") or {}).get("capabilities") or {}
    if "webRoutes" in capabilities and "remoteEndpoints" in capabilities:
        return
    await assess_existing_installation(
        row, repository=repository, dsh_version=await running_dsh_version(),
    )
