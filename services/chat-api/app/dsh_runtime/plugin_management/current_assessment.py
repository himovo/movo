"""Assess a stored plugin against the installed DSH Runtime before enabling it."""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.dsh_runtime.plugin_management.failed_assessment import failed_assessment
from app.dsh_runtime.plugin_management.installer import DshPluginInstaller, PluginInstallError
from app.dsh_runtime.plugin_management.repository import PluginInstallationRepository
from app.dsh_runtime.transport import HttpKernelHostTransport


async def running_dsh_version() -> str:
    settings = get_settings()
    transport = HttpKernelHostTransport(
        settings.DSH_RUNTIME_HOST_URL,
        access_token=settings.DSH_RUNTIME_HOST_TOKEN,
    )
    try:
        health = await transport.request("GET", "/health")
    finally:
        await transport.close()
    if health.get("ok") is not True or health.get("kernel") != "dsh" or not health.get("version"):
        raise RuntimeError("DSH Runtime Host is not healthy")
    return str(health["version"])


async def assess_existing_installation(
    row: dict[str, Any], *, repository: PluginInstallationRepository,
    dsh_version: str,
) -> dict[str, Any] | None:
    try:
        package = await DshPluginInstaller().inspect_and_install(
            str(row["spec"]),
            archive_id=str(row.get("archive_id") or ""),
            archive_digest=str(row.get("archive_digest") or ""),
        )
        if package.get("name") != row.get("name") or package.get("version") != row.get("version"):
            raise PluginInstallError("plugin_package_changed", code="plugin-package-changed")
        availability = package["availability"]
        tool_names = package["tool_names"]
        registry = package.get("registry", "")
    except PluginInstallError as exc:
        availability = failed_assessment(
            exc, dsh_version=dsh_version,
            plugin_version=str(row.get("version") or ""),
        )
        tool_names = []
        registry = ""
    return await repository.update_assessment(
        main_id=str(row["main_id"]),
        user_id=str(row.get("owner_user_id") or ""),
        plugin_id=str(row["_id"]),
        availability=availability, tool_names=tool_names, registry=registry,
        expected_version=str(row["version"]), expected_spec=str(row["spec"]),
    )
