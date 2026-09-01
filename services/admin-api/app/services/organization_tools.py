from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.db import get_db


def organization_scope_clause() -> dict[str, Any]:
    """Match explicit organization tools and legacy tools without a scope."""
    return {"$or": [{"scope": "organization"}, {"scope": {"$exists": False}}, {"scope": ""}]}


def organization_tool_query(main_id: str, **conditions: Any) -> dict[str, Any]:
    return {"main_id": str(main_id), **conditions, **organization_scope_clause()}


def organization_tool_fields() -> dict[str, str]:
    return {"scope": "organization", "owner_user_id": ""}


def replace_tool_id(tool_ids: list[Any], old_id: str, new_id: str) -> list[str]:
    result: list[str] = []
    for item in tool_ids:
        value = new_id if str(item) == old_id else str(item)
        if value and value not in result:
            result.append(value)
    return result


async def repair_role_referenced_personal_tools(db: Any | None = None) -> dict[str, int]:
    """Repair the historical state where a position role references a personal tool.

    A role assignment is an explicit enterprise-governance decision. If an equivalent
    organization tool already exists, roles are rewired to it. Otherwise the referenced
    tool is promoted in place, preserving its stable ID and credentials.
    """
    database = db or get_db()
    roles = await database.position_roles.find(
        {"tool_access_mode": "selected", "tool_ids.0": {"$exists": True}},
        {"main_id": 1, "tool_ids": 1},
    ).to_list(length=10000)
    referenced: dict[tuple[str, str], None] = {}
    for role in roles:
        main_id = str(role.get("main_id") or "")
        for tool_id in role.get("tool_ids") or []:
            if main_id and tool_id:
                referenced[(main_id, str(tool_id))] = None

    promoted = 0
    rewired = 0
    now = datetime.now(timezone.utc)
    for main_id, tool_id in referenced:
        personal = await database.external_tools.find_one({
            "_id": tool_id,
            "main_id": main_id,
            "scope": "user",
        })
        if personal is None:
            continue
        equivalent = await database.external_tools.find_one(organization_tool_query(
            main_id,
            name=personal.get("name"),
            type=personal.get("type"),
        ))
        replacement_id = str((equivalent or {}).get("_id") or tool_id)
        if equivalent is None:
            await database.external_tools.update_one(
                {"_id": tool_id, "main_id": main_id, "scope": "user"},
                {"$set": {**organization_tool_fields(), "updated_at": now}},
            )
            promoted += 1
            continue

        affected_roles = [
            role for role in roles
            if str(role.get("main_id") or "") == main_id and tool_id in [str(item) for item in role.get("tool_ids") or []]
        ]
        for role in affected_roles:
            updated_ids = replace_tool_id(role.get("tool_ids") or [], tool_id, replacement_id)
            await database.position_roles.update_one(
                {"_id": role.get("_id"), "main_id": main_id},
                {"$set": {"tool_ids": updated_ids, "updated_at": now}},
            )
            rewired += 1

    return {"promoted": promoted, "rewired": rewired}
