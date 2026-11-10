"""Compare capabilities reported by DSH before and after one bundle activation."""

from __future__ import annotations

import json
import re
from typing import Any


def _added(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> list[dict[str, Any]]:
    known = {json.dumps(item, sort_keys=True) for item in before if isinstance(item, dict)}
    return [item for item in after if isinstance(item, dict)
            and json.dumps(item, sort_keys=True) not in known]


def _new_providers(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing = {str(item.get("id") or "") for item in before if isinstance(item, dict)}
    return [item for item in after if isinstance(item, dict)
            and item.get("id") and str(item["id"]) not in existing]


def projected_capabilities(
    baseline: dict[str, Any], activated: dict[str, Any],
    baseline_session: dict[str, Any], activated_session: dict[str, Any],
    bundle_name: str, discovered_tools: list[str] | None = None,
) -> dict[str, Any]:
    bundle = next((item for item in activated.get("bundles") or []
                   if item.get("name") == bundle_name), {})
    module_names = {bundle_name}
    module_names.update(str(row.get("moduleName") or "") for row in bundle.get("rows") or []
                        if isinstance(row, dict))
    mcp_servers: dict[str, list[str]] = {}
    for tool in discovered_tools or []:
        match = re.fullmatch(r"mcp__([A-Za-z0-9_-]{1,32})__(.+)", tool)
        if match:
            mcp_servers.setdefault(match[1], []).append(match[2])
    return {
        "skills": _added(baseline_session.get("skills", []),
                         activated_session.get("skills", [])),
        "commands": _added(baseline_session.get("commands") or [],
                           activated_session.get("commands") or []),
        "modelProviders": _new_providers(
            baseline_session.get("modelProviders") or baseline.get("modelProviders") or [],
            activated_session.get("modelProviders") or activated.get("modelProviders") or [],
        ),
        "clientModules": [item for item in _added(
            baseline_session.get("clientModules") or baseline.get("clientModules") or [],
            activated_session.get("clientModules") or activated.get("clientModules") or [],
        ) if item.get("id") in module_names],
        "webRoutes": _added(
            baseline_session.get("webRoutes") or baseline.get("webRoutes") or [],
            activated_session.get("webRoutes") or activated.get("webRoutes") or [],
        ),
        "remoteEndpoints": sorted(set(
            activated_session.get("remoteEndpoints") or activated.get("remoteEndpoints") or []
        ) - set(
            baseline_session.get("remoteEndpoints") or baseline.get("remoteEndpoints") or []
        )),
        "mcpServers": [{"name": name, "tools": sorted(set(names))}
                       for name, names in sorted(mcp_servers.items())],
        "rows": [{"rowId": str(row.get("rowId") or ""),
                  "moduleName": str(row.get("moduleName") or ""),
                  "entryId": str(row.get("entryId") or "")}
                 for row in bundle.get("rows") or [] if isinstance(row, dict)],
        "overrides": [str(item) for item in bundle.get("overrides") or []],
    }
