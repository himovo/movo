"""Read-only DSH bundle inspection before an installation is attempted."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from app.core.config import get_settings
from app.dsh_runtime.errors import DshTransportError
from app.dsh_runtime.transport import HttpKernelHostTransport
from app.dsh_runtime.plugin_management.installer import PluginInstallError
from app.dsh_runtime.plugin_management.offline_package_capture import initialize_package_source, imported_plugin_record
from app.dsh_runtime.plugin_management.source_policy import is_fixed_npm_source

logger = logging.getLogger(__name__)


def _public_registry(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        return None
    return urlunsplit((parsed.scheme, parsed.netloc.rsplit("@", 1)[-1], parsed.path, "", ""))


async def inspect_plugin_spec(spec: str) -> dict:
    spec = spec.strip()
    if not spec or len(spec) > 500 or any(ord(ch) < 32 for ch in spec):
        raise PluginInstallError("Invalid DSH plugin spec")
    await initialize_package_source()
    offline_only = (Path(os.environ.get("MOVO_OFFLINE_PACKAGE_ROOT", "/offline-packages")) / "offline-only").is_file()
    inspect_spec = spec
    offline_source_dsh_version = ""
    if offline_only and is_fixed_npm_source(spec):
        archive_path, offline_source_dsh_version = imported_plugin_record(spec)
        inspect_spec = archive_path or ""
    settings = get_settings()
    transport = HttpKernelHostTransport(
        settings.DSH_RUNTIME_HOST_URL, timeout_seconds=90,
        startup_timeout_seconds=90, access_token=settings.DSH_RUNTIME_HOST_TOKEN,
    )
    runtime_id = ""
    try:
        health = await transport.request("GET", "/health")
        version = str(health.get("version") or "unknown")
        locked = str(health.get("lockedVersion") or "unknown")
        if version != locked:
            raise PluginInstallError(
                f"dsh_runtime_version_mismatch: installed {version}, locked {locked}",
                code="dsh-runtime-version-mismatch", dsh_version=version,
            )
        if health.get("ok") is not True or health.get("kernel") != "dsh":
            raise PluginInstallError("dsh_runtime_unavailable", code="dsh-runtime-unavailable")
        if not inspect_spec:
            return {"spec": spec, "dshVersion": version, "lockedVersion": locked, "status": "refused",
                    "problem": "plugin_offline_package_missing", "diagnostic": "plugin_offline_package_missing",
                    "offlineSourceDshVersion": offline_source_dsh_version or None}
        runtime = await transport.request("POST", "/v1/runtimes", json={
            "isolationKey": f"plugin-preflight:{uuid4()}",
            "profileVersion": "plugin-preflight",
            "modelProfile": {
                "profileVersion": "plugin-preflight",
                "modelInstanceId": "plugin-preflight",
                "modelName": "plugin-preflight",
                "gatewayUrl": "http://127.0.0.1/validation-only",
                "accessToken": "plugin-preflight",
                "plugins": [],
            },
        })
        runtime_id = str(runtime["runtimeId"])
        path = f"/v1/runtimes/{runtime_id}/managed-plugins/inspect"
        inspected = await transport.request("POST", path, json={"spec": inspect_spec})
        if inspected.get("problem") == "not-found" and is_fixed_npm_source(spec) and not offline_only:
            fallback = await transport.request("POST", path, json={
                "spec": spec, "registry": "https://registry.npmjs.org/",
            })
            if fallback.get("status") == "accepted" or fallback.get("problem") in {"network", "not-found"}:
                inspected = fallback
        if inspected.get("problem") == "already-installed":
            inventory = await transport.request("GET", f"/v1/runtimes/{runtime_id}/managed-plugins")
            builtin = next((item for item in inventory.get("bundles", [])
                            if item.get("optional") and spec == f"{item.get('name')}@{item.get('version')}"), None)
            if builtin:
                inspected = {"status": "accepted", "kind": "builtin", "name": builtin["name"],
                             "version": builtin["version"], "registry": None}
        if inspected.get("status") == "accepted" and inspected.get("kind") == "registry" and not is_fixed_npm_source(spec):
            inspected = {"status": "refused", "problem": "fixed_plugin_version_required",
                         "reason": "A registry plugin requires an exact version"}
        return {
            "spec": spec,
            "dshVersion": version,
            "lockedVersion": locked,
            "offlineSourceDshVersion": offline_source_dsh_version or None,
            "status": (
                "pending_runtime_validation" if inspected.get("status") == "accepted"
                and inspected.get("name") and inspected.get("version")
                else "unverified" if inspected.get("status") == "accepted" else "refused"
            ),
            "name": inspected.get("name"),
            "version": inspected.get("version"),
            "description": inspected.get("description"),
            "kind": inspected.get("kind"),
            "registry": _public_registry(inspected.get("registry")),
            "problem": inspected.get("problem"),
            "diagnostic": inspected.get("reason"),
        }
    except DshTransportError as exc:
        raise PluginInstallError(str(exc)) from exc
    finally:
        try:
            if runtime_id:
                try:
                    await transport.request("DELETE", f"/v1/runtimes/{runtime_id}", params={"purge": "1"})
                except Exception as exc:
                    logger.warning("temporary DSH plugin preflight cleanup failed: %s", exc)
        finally:
            await transport.close()
