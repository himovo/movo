"""Effective DSH plugin declarations for one tenant and one user."""

from __future__ import annotations

import json
from typing import Any

from app.core.db import get_db
from app.execution_isolation import ExecutionTarget, route_plugin
from app.product.resource_access import filter_allowed_resource_ids
from app.product.execution_access import execution_is_allowed
from app.dsh_runtime.plugin_management.tool_requirements import tool_requirements


class MongoPluginCatalog:
    async def list_enabled(self, tenant_id: str, user_id: str) -> tuple[dict[str, Any], ...]:
        if not await execution_is_allowed(
            main_id=tenant_id, user_id=user_id, capability="plugin.runtime",
        ):
            return ()
        rows = await get_db().dsh_plugin_installations.find({
            "main_id": tenant_id,
            "$or": [{"enabled": True}, {"owner_user_id": ""}],
            "owner_user_id": {"$in": ["", user_id]},
            "engine": "dsh",
        }).sort([("owner_user_id", 1), ("name", 1)]).to_list(length=None)
        organization_rows = [row for row in rows if not row.get("owner_user_id")]
        allowed_ids = await filter_allowed_resource_ids(
            "plugin", main_id=tenant_id, user_id=user_id,
            resource_ids=(str(row["_id"]) for row in organization_rows),
        ) if user_id else {str(row["_id"]) for row in organization_rows}
        denied_names = {
            str(row.get("name") or "") for row in organization_rows
            if str(row["_id"]) not in allowed_ids
        }
        effective: dict[str, dict[str, Any]] = {}
        for row in rows:
            if route_plugin(row) is not ExecutionTarget.PLUGIN_RUNTIME_CONTAINER:
                continue
            name = str(row.get("name") or "")
            if not name or not row.get("enabled", True) or name in denied_names or (
                not row.get("owner_user_id") and str(row["_id"]) not in allowed_ids
            ):
                continue
            requirements = tool_requirements(
                name, str(row.get("version") or ""), list(row.get("tool_names") or []),
            )
            # A user's own version takes precedence over the tenant default.
            effective[name] = {
                "name": name,
                "version": str(row.get("version") or ""),
                "spec": str(row.get("spec") or ""),
                **({"registry": str(row["registry"])} if row.get("registry") else {}),
                "source_scope": "personal" if row.get("owner_user_id") else "organization",
                "tool_names": list(row.get("tool_names") or []),
                **({"tool_requirements": requirements} if requirements else {}),
                **({"archive_id": row["archive_id"], "archive_digest": row["archive_digest"]}
                   if row.get("archive_id") else {}),
            }
        return tuple(effective[name] for name in sorted(effective))


def plugin_versions(plugins: tuple[dict[str, Any], ...]) -> tuple[str, ...]:
    return tuple(
        f"{item['source_scope']}:{item['name']}@{item['version']}:{item['spec']}:{item.get('registry', '')}:{item.get('archive_digest', '')}:{','.join(item.get('tool_names') or [])}"
        + (f":{json.dumps(item['tool_requirements'], sort_keys=True)}" if item.get('tool_requirements') else "")
        for item in plugins
    )
