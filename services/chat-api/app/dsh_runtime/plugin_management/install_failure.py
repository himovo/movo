"""Interpret DSH package-manager failures without discarding their diagnostics."""

from __future__ import annotations

from typing import Any


def install_error_code(result: dict[str, Any]) -> str:
    error = result.get("error") or {}
    return str(error.get("code") or "") if isinstance(error, dict) else ""


def install_error_text(result: dict[str, Any]) -> str:
    error = result.get("error") or {}
    if isinstance(error, str):
        return error
    if isinstance(error, dict):
        if error.get("code") == "incompatible-version":
            mismatches = []
            for item in error.get("incompatible") or (result.get("packageResult") or {}).get("incompatible") or []:
                if not isinstance(item, dict):
                    continue
                peers = item.get("peers") or {}
                requirement = ", ".join(f"{name} {version}" for name, version in peers.items()) if isinstance(peers, dict) else ""
                mismatches.append(f"{item.get('name', 'plugin')}@{item.get('version', '?')} requires {requirement}; DSH {item.get('runtimeVersion', '?')}")
            if mismatches:
                return "incompatible-version: " + "; ".join(mismatches)
        return ": ".join(str(value) for value in (
            error.get("code"), error.get("diagnostic") or error.get("message") or error.get("reason"),
        ) if value) or "Plugin installation failed"
    return str(error)


def is_missing_registry_dependency(result: dict[str, Any]) -> bool:
    diagnostic = install_error_text(result)
    return "ERR_PNPM_NO_MATCHING_VERSION" in diagnostic or "No matching version found" in diagnostic
