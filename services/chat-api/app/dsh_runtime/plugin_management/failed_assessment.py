"""Create a stable compatibility state from an installer failure."""

from __future__ import annotations

from typing import Any

from app.dsh_runtime.plugin_management.installer import PluginInstallError


def failed_assessment(exc: PluginInstallError, *, dsh_version: str, plugin_version: str) -> dict[str, Any]:
    incompatible = exc.code == "incompatible-version" or str(exc).split(":", 1)[0] == "incompatible-version"
    return {
        "status": "version_incompatible" if incompatible else "failed",
        "reason": str(exc),
        "error_code": exc.code,
        "dsh_version": exc.dsh_version or dsh_version,
        "plugin_version": plugin_version,
        "checks": {"package": False, "runtime": False,
                   "session": False, "invocation": False},
    }
