"""Use DSH's own manager to validate and install before recording a bundle."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import get_settings
from app.dsh_runtime.transport import HttpKernelHostTransport
from app.dsh_runtime.errors import DshTransportError
from app.dsh_runtime.plugin_management.source_policy import is_fixed_npm_source
from app.dsh_runtime.plugin_management.install_failure import install_error_code, install_error_text, is_missing_registry_dependency
from app.dsh_runtime.plugin_management.compatibility import classify_conversation_tools
from app.dsh_runtime.plugin_management.release_compatibility import incompatible_release
from app.dsh_runtime.plugin_management.capability_projection import projected_capabilities
from app.dsh_runtime.plugin_management.tool_requirements import tool_requirements
from app.dsh_runtime.plugin_management.offline_package_capture import initialize_package_source, imported_plugin_record, record_plugin

logger = logging.getLogger(__name__)
NPM_REGISTRY = "https://registry.npmjs.org/"


class PluginInstallError(ValueError):
    def __init__(self, message: str, *, code: str = "", dsh_version: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.dsh_version = dsh_version


class DshPluginInstaller:
    async def inspect_and_install(self, spec: str, *, archive_id: str = "", archive_digest: str = "") -> dict[str, Any]:
        spec = spec.strip()
        if not spec or len(spec) > 500 or any(ord(ch) < 32 for ch in spec):
            raise PluginInstallError("Invalid DSH plugin spec")
        requested_spec = spec
        settings = get_settings()
        await initialize_package_source()
        offline_only = (Path(os.environ.get("MOVO_OFFLINE_PACKAGE_ROOT", "/offline-packages")) / "offline-only").is_file()
        offline_source_dsh_version = ""
        if offline_only and not archive_id and is_fixed_npm_source(spec):
            archive_path, offline_source_dsh_version = imported_plugin_record(spec)
            spec = archive_path or spec
        transport = HttpKernelHostTransport(
            settings.DSH_RUNTIME_HOST_URL,
            timeout_seconds=300,
            startup_timeout_seconds=300,
            access_token=settings.DSH_RUNTIME_HOST_TOKEN,
        )
        runtime_ids: list[str] = []
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
            if archive_id:
                materialized = await transport.request("POST", "/v1/plugin-archives/materialize", json={
                    "archiveId": archive_id,
                    "digest": archive_digest,
                    "gatewayUrl": settings.DSH_TOOL_GATEWAY_URL.removesuffix("/tools") + "/plugin-archives",
                    "accessToken": settings.DSH_RUNTIME_HOST_TOKEN,
                })
                spec = str(materialized["spec"])
            runtime = await transport.request("POST", "/v1/runtimes", json={
                "isolationKey": f"plugin-install-validation:{uuid4()}",
                "profileVersion": "plugin-install-validation",
                "modelProfile": {
                    "profileVersion": "plugin-install-validation",
                    "modelInstanceId": "plugin-install-validation",
                    "modelName": "plugin-install-validation",
                    "gatewayUrl": "http://127.0.0.1/validation-only",
                    "accessToken": "plugin-install-validation",
                    "plugins": [],
                },
            })
            runtime_id = str(runtime["runtimeId"])
            runtime_ids.append(runtime_id)
            path = f"/v1/runtimes/{runtime_id}/managed-plugins"
            original_inventory = await transport.request("GET", path)
            source_dsh_mismatch = bool(offline_source_dsh_version and
                                       offline_source_dsh_version != str(original_inventory.get("dshVersion") or ""))
            baseline_session = await transport.request(
                "POST", f"/v1/runtimes/{runtime_id}/sessions",
                json={"sessionId": f"plugin-baseline-{uuid4()}"},
            )
            baseline_capabilities = await transport.request(
                "GET", f"/v1/runtimes/{runtime_id}/sessions/{baseline_session['sessionId']}/plugin-capabilities",
            )
            inspected = await transport.request("POST", f"{path}/inspect", json={"spec": spec})
            if inspected.get("status") == "accepted" and inspected.get("kind") == "registry" and not is_fixed_npm_source(requested_spec):
                raise PluginInstallError("fixed_plugin_version_required", code="fixed_plugin_version_required",
                                         dsh_version=version)
            install_registry = ""
            if inspected.get("problem") == "not-found" and is_fixed_npm_source(spec) and not offline_only:
                # A configured mirror can lag behind npm. Retry the exact
                # version at the canonical registry before declaring it absent.
                inspected = await transport.request(
                    "POST", f"{path}/inspect", json={"spec": spec, "registry": NPM_REGISTRY},
                )
                if inspected.get("status") == "accepted":
                    install_registry = NPM_REGISTRY
                elif inspected.get("problem") == "network":
                    raise PluginInstallError("plugin_registry_unavailable")
            package = None
            if inspected.get("status") == "refused" and inspected.get("problem") == "already-installed":
                bundles = await transport.request("GET", path)
                builtin = next(
                    (item for item in bundles.get("bundles", [])
                     if item.get("optional") and spec == f"{item.get('name')}@{item.get('version')}"),
                    None,
                )
                if builtin:
                    activated = await transport.request("POST", f"{path}/enable", json={
                        "name": builtin["name"], "enabled": True,
                    })
                    if activated.get("application") != "failed" and not activated.get("error"):
                        package = {
                            "name": str(builtin["name"]),
                            "version": str(builtin["version"]),
                            "description": str(builtin.get("description") or ""),
                            "spec": spec,
                        }
            release_compatibility_checked = package is not None
            if package is None and inspected.get("status") != "accepted":
                problem = str(inspected.get("problem") or "not-a-bundle")
                raise PluginInstallError(
                    "plugin_offline_package_missing" if offline_only and problem in ("not-found", "network") and is_fixed_npm_source(spec)
                    else "plugin_package_not_found" if problem == "not-found" and is_fixed_npm_source(spec) else problem
                )
            if package is None:
                installed = await transport.request("POST", f"{path}/install", json={
                    "spec": spec, **({"registry": install_registry} if install_registry else {}),
                })
                if ((installed.get("application") == "failed" or installed.get("error"))
                        and not install_registry and is_fixed_npm_source(spec) and not offline_only
                        and is_missing_registry_dependency(installed)):
                    official = await transport.request(
                        "POST", f"{path}/inspect", json={"spec": spec, "registry": NPM_REGISTRY},
                    )
                    if official.get("status") == "accepted":
                        install_registry = NPM_REGISTRY
                        installed = await transport.request("POST", f"{path}/install", json={
                            "spec": spec, "registry": install_registry,
                        })
                if installed.get("application") == "failed" or installed.get("error"):
                    raise PluginInstallError(
                        install_error_text(installed), code=install_error_code(installed),
                        dsh_version=str(original_inventory.get("dshVersion") or ""),
                    )
                name = str(installed.get("bundle") or "")
                version = str(installed.get("version") or "")
                if not name or not version:
                    raise PluginInstallError("DSH plugin installation returned an inconsistent package")
                bundles = await transport.request("GET", path)
                installed_bundle = next(
                    (item for item in bundles.get("bundles", []) if item.get("name") == name), None,
                )
                if not installed_bundle or installed_bundle.get("version") != version:
                    raise PluginInstallError("DSH plugin package was not found after installation")
                manifest = await transport.request("POST", f"{path}/manifest", json={"name": name})
                if manifest.get("version") != version:
                    raise PluginInstallError("DSH plugin manifest version did not match the installed package")
                mismatch = incompatible_release(manifest, str(original_inventory.get("dshVersion") or health.get("version") or ""))
                if mismatch:
                    raise PluginInstallError(mismatch, code="incompatible-version",
                                             dsh_version=str(original_inventory.get("dshVersion") or ""))
                release_compatibility_checked = True
                package = {
                    "name": name,
                    "version": version,
                    "description": str(installed_bundle.get("description") or ""),
                    "spec": f"{name}@{version}" if inspected.get("kind") == "registry" else spec,
                    "registry": install_registry,
                }
            # A DSH install can succeed while the bundle's rows stay pending.
            # Boot it in its own disposable Runtime before making it selectable.
            try:
                validation = await transport.request("POST", "/v1/runtimes", json={
                    "isolationKey": f"plugin-install-validation:{uuid4()}",
                    "profileVersion": "plugin-install-validation-active",
                    "modelProfile": {
                        "profileVersion": "plugin-install-validation-active",
                        "modelInstanceId": "plugin-install-validation",
                        "modelName": "plugin-install-validation",
                        "gatewayUrl": "http://127.0.0.1/validation-only",
                        "accessToken": "plugin-install-validation",
                        "plugins": [{**package, "source_scope": "personal"}],
                    },
                })
            except DshTransportError as exc:
                package["tool_names"] = []
                package["availability"] = {
                    "status": "failed", "reason": str(exc),
                    "dsh_version": str(original_inventory.get("dshVersion") or ""),
                    "plugin_version": package["version"],
                    "checks": {"package": True, "runtime": False, "session": False, "invocation": False},
                    **({"offline_source_dsh_version": offline_source_dsh_version,
                        "offline_source_dsh_mismatch": source_dsh_mismatch} if offline_source_dsh_version else {}),
                }
                if archive_id:
                    package["spec"] = f"archive:{archive_digest}"
                    package["archive_id"] = archive_id
                    package["archive_digest"] = archive_digest
                await record_plugin(package["name"], package["version"], archive_digest,
                                    str(original_inventory.get("dshVersion") or ""))
                return package
            runtime_ids.append(str(validation["runtimeId"]))
            activated_inventory = await transport.request(
                "GET", f"/v1/runtimes/{validation['runtimeId']}/managed-plugins",
            )
            base_tools = set(original_inventory.get("globalTools") or [])
            package["tool_names"] = sorted(
                name for name in activated_inventory.get("globalTools") or []
                if name not in base_tools
            )
            discovered = package["tool_names"]
            requirements = tool_requirements(package["name"], package["version"], discovered)
            workspace_tools = sorted(
                name for name, needed in requirements.items() if "workspace" in needed
            )
            exposed: set[str] = set()
            activated_capabilities: dict[str, Any] = {}
            if discovered or activated_inventory.get("skills") or activated_inventory.get("bundles"):
                try:
                    # The first Runtime discovers root tools. A new immutable
                    # Profile must declare them before MOVO's allow-list can
                    # expose them to the agent in a Session.
                    session_validation = await transport.request("POST", "/v1/runtimes", json={
                        "isolationKey": f"plugin-install-validation:{uuid4()}",
                        "profileVersion": "plugin-install-validation-session",
                        "modelProfile": {
                            "profileVersion": "plugin-install-validation-session",
                            "modelInstanceId": "plugin-install-validation",
                            "modelName": "plugin-install-validation",
                            "gatewayUrl": "http://127.0.0.1/validation-only",
                            "accessToken": "plugin-install-validation",
                            "plugins": [{
                                **package, "source_scope": "personal",
                                "tool_requirements": requirements,
                            }],
                        },
                    })
                    runtime_ids.append(str(session_validation["runtimeId"]))
                    workspace_id = None
                    if workspace_tools:
                        workspace = await transport.request(
                            "POST",
                            f"/v1/runtimes/{session_validation['runtimeId']}/workspaces",
                            json={"path": "/tmp", "title": "Plugin validation"},
                        )
                        workspace_id = str(workspace["workspaceId"])
                    session = await transport.request(
                        "POST", f"/v1/runtimes/{session_validation['runtimeId']}/sessions",
                        json={
                            "sessionId": f"plugin-validation-{uuid4()}",
                            **({"workspaceId": workspace_id} if workspace_id else {}),
                        },
                    )
                    exposed = set(session.get("capabilityTools") or [])
                    activated_capabilities = await transport.request(
                        "GET", f"/v1/runtimes/{session_validation['runtimeId']}/sessions/{session['sessionId']}/plugin-capabilities",
                    )
                except DshTransportError as exc:
                    package["availability"] = {
                        "status": "failed", "reason": str(exc),
                        "dsh_version": str(original_inventory.get("dshVersion") or ""),
                        "plugin_version": package["version"],
                        "checks": {"package": True, "runtime": True, "session": False, "invocation": False},
                        "discovered_tools": discovered,
                        **({"offline_source_dsh_version": offline_source_dsh_version,
                            "offline_source_dsh_mismatch": source_dsh_mismatch} if offline_source_dsh_version else {}),
                    }
                    if archive_id:
                        package["spec"] = f"archive:{archive_digest}"
                        package["archive_id"] = archive_id
                        package["archive_digest"] = archive_digest
                    await record_plugin(package["name"], package["version"], archive_digest,
                                        str(original_inventory.get("dshVersion") or ""))
                    return package
            capabilities = projected_capabilities(
                original_inventory, activated_inventory,
                baseline_capabilities, activated_capabilities, package["name"],
                sorted(exposed.intersection(discovered)),
            )
            status, reason = classify_conversation_tools(set(discovered), exposed)
            if status == "runtime_active" and any(capabilities.get(key) for key in ("skills", "commands", "clientModules", "modelProviders", "mcpServers", "rows")):
                reason = "other_capabilities_available"
            package["availability"] = {
                "status": status,
                "reason": reason,
                "dsh_version": str(activated_inventory.get("dshVersion") or ""),
                "plugin_version": package["version"],
                "release_compatibility_checked": release_compatibility_checked,
                "checks": {"package": True, "runtime": True, "session": status in ("session_exposed", "runtime_active"), "invocation": False},
                "discovered_tools": discovered,
                "session_tools": sorted(exposed.intersection(discovered)),
                "workspace_required_tools": workspace_tools,
                "capabilities": capabilities,
                **({"offline_source_dsh_version": offline_source_dsh_version,
                    "offline_source_dsh_mismatch": source_dsh_mismatch} if offline_source_dsh_version else {}),
            }
            if archive_id:
                package["spec"] = f"archive:{archive_digest}"
                package["archive_id"] = archive_id
                package["archive_digest"] = archive_digest
            await record_plugin(package["name"], package["version"], archive_digest,
                                str(activated_inventory.get("dshVersion") or ""))
            return package
        except DshTransportError as exc:
            raise PluginInstallError(str(exc)) from exc
        finally:
            try:
                for runtime_id in reversed(runtime_ids):
                    try:
                        await transport.request("DELETE", f"/v1/runtimes/{runtime_id}", params={"purge": "1"})
                    except Exception as exc:
                        logger.warning("temporary DSH plugin Runtime cleanup failed: %s", exc)
            finally:
                await transport.close()
