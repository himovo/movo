"""Recheck installed plugins when the running DSH version changes."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import get_settings
from app.dsh_runtime.plugin_management.installer import DshPluginInstaller, PluginInstallError
from app.dsh_runtime.plugin_management.failed_assessment import failed_assessment
from app.dsh_runtime.plugin_management.repository import PluginInstallationRepository
from app.dsh_runtime.transport import HttpKernelHostTransport


logger = logging.getLogger(__name__)


def needs_revalidation(row: dict[str, Any], dsh_version: str) -> bool:
    availability = row.get("availability") or {}
    if str(availability.get("dsh_version") or "") != dsh_version:
        return True
    if availability.get("status") in {"session_exposed", "runtime_active", "verified"} and not availability.get("release_compatibility_checked"):
        return True
    if needs_surface_refresh(row, dsh_version):
        return True
    if availability.get("status") == "unverified" and availability.get("reason") in {
        "revalidation_in_progress", "dsh_version_changed",
    }:
        started_at = availability.get("revalidation_started_at")
        if not isinstance(started_at, datetime):
            return True
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        return started_at <= datetime.now(timezone.utc) - timedelta(minutes=15)
    if availability.get("status") != "failed":
        return False
    last_change = row.get("updated_at")
    if not isinstance(last_change, datetime):
        return True
    if last_change.tzinfo is None:
        last_change = last_change.replace(tzinfo=timezone.utc)
    return last_change <= datetime.now(timezone.utc) - timedelta(minutes=5)


def needs_surface_refresh(row: dict[str, Any], dsh_version: str) -> bool:
    availability = row.get("availability") or {}
    if availability.get("status") not in {"session_exposed", "runtime_active", "verified"}:
        return False
    if availability.get("dsh_version") != dsh_version or not availability.get("release_compatibility_checked"):
        return False
    modules = (availability.get("capabilities") or {}).get("clientModules") or []
    return any("conversationView" not in item for item in modules if isinstance(item, dict))


async def revalidate_installed_plugins(
    *, repository: PluginInstallationRepository | None = None,
    installer: DshPluginInstaller | None = None,
    transport: HttpKernelHostTransport | None = None,
) -> None:
    repository = repository or PluginInstallationRepository()
    installer = installer or DshPluginInstaller()
    owns_transport = transport is None
    if transport is None:
        settings = get_settings()
        transport = HttpKernelHostTransport(
            settings.DSH_RUNTIME_HOST_URL,
            access_token=settings.DSH_RUNTIME_HOST_TOKEN,
        )
    try:
        health = await transport.request("GET", "/health")
        if health.get("ok") is not True or health.get("kernel") != "dsh":
            return
        dsh_version = str(health.get("version") or "")
        if not dsh_version:
            return
        await repository.restore_legacy_surface_pending(dsh_version)
        for row in await repository.list_enabled_installations():
            if not needs_revalidation(row, dsh_version):
                continue
            surface_only = needs_surface_refresh(row, dsh_version)
            if not await repository.mark_revalidation_pending(row, dsh_version, surface_only=surface_only):
                continue
            try:
                package = await installer.inspect_and_install(
                    str(row["spec"]),
                    archive_id=str(row.get("archive_id") or ""),
                    archive_digest=str(row.get("archive_digest") or ""),
                )
                if package.get("name") != row.get("name") or package.get("version") != row.get("version"):
                    raise PluginInstallError("plugin_package_changed", code="plugin-package-changed")
                availability = package["availability"]
                if surface_only:
                    previous = row.get("availability") or {}
                    availability = {
                        **availability,
                        "status": previous["status"],
                        "reason": previous.get("reason", availability.get("reason")),
                        "checks": previous.get("checks", availability.get("checks", {})),
                        **({"last_invocation": previous["last_invocation"]}
                           if previous.get("last_invocation") else {}),
                    }
                tool_names = package["tool_names"]
                registry = package.get("registry", "")
            except PluginInstallError as exc:
                if surface_only:
                    logger.warning("DSH plugin surface refresh failed: %s", exc)
                    await repository.clear_surface_refresh(row)
                    continue
                availability = failed_assessment(
                    exc, dsh_version=dsh_version,
                    plugin_version=str(row.get("version") or ""),
                )
                tool_names = []
                registry = ""
            except Exception:
                logger.exception("DSH plugin compatibility check interrupted", extra={
                    "installation_id": str(row["_id"]),
                })
                if surface_only:
                    await repository.clear_surface_refresh(row)
                    continue
                availability = failed_assessment(
                    PluginInstallError(
                        "plugin_revalidation_interrupted", code="revalidation_interrupted",
                        dsh_version=dsh_version,
                    ),
                    dsh_version=dsh_version,
                    plugin_version=str(row.get("version") or ""),
                )
                tool_names = []
                registry = ""
            try:
                await repository.update_assessment(
                    main_id=str(row["main_id"]),
                    user_id=str(row.get("owner_user_id") or ""),
                    plugin_id=str(row["_id"]),
                    availability=availability, tool_names=tool_names,
                    registry=registry,
                    expected_version=str(row["version"]), expected_spec=str(row["spec"]),
                    expected_pending_target=dsh_version,
                    expected_surface_refresh=surface_only,
                )
            except Exception:
                logger.exception("Could not persist DSH plugin compatibility result", extra={
                    "installation_id": str(row["_id"]),
                })
    finally:
        if owns_transport:
            await transport.close()


async def monitor_plugin_compatibility(interval_seconds: float = 300) -> None:
    while True:
        try:
            await revalidate_installed_plugins()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("DSH plugin compatibility revalidation failed")
        await asyncio.sleep(interval_seconds)
