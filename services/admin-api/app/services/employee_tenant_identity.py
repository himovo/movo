from __future__ import annotations

from typing import Any

from app.core.db import get_db


def employee_tenant_fields(main_id: str, org_name: str) -> dict[str, str]:
    normalized_name = str(org_name or "").strip() or str(main_id)
    return {
        "org_name": normalized_name,
        "space_type": "personal" if normalized_name == "个人空间" else "enterprise",
    }


def authoritative_tenant_names(
    organizations: list[dict[str, Any]],
    admin_rows: list[dict[str, Any]],
) -> dict[str, str]:
    """Prefer configured admin identity when billing metadata is stale."""
    names = {
        str(row.get("main_id")): str(row.get("org_name") or "").strip()
        for row in organizations
        if str(row.get("org_name") or "").strip()
    }
    names.update({
        str(row.get("main_id")): str(row.get("org_name") or "").strip()
        for row in admin_rows
        if str(row.get("org_name") or "").strip()
    })
    return names


async def repair_employee_tenant_identities(db: Any | None = None) -> int:
    database = db or get_db()
    organizations = await database.organizations.find(
        {"main_id": {"$nin": [None, "", "default"]}}, {"main_id": 1, "org_name": 1}
    ).to_list(length=10000)
    admin_rows = await database.admin_accounts.find(
        {"main_id": {"$nin": [None, "", "default"]}}, {"main_id": 1, "org_name": 1}
    ).to_list(length=10000)
    names = authoritative_tenant_names(organizations, admin_rows)
    admin_names = authoritative_tenant_names([], admin_rows)
    repaired = 0
    for main_id, org_name in names.items():
        fields = employee_tenant_fields(main_id, org_name)
        identity_result = await database.end_users.update_many(
            {"main_id": main_id},
            {"$set": fields},
        )
        repaired += int(identity_result.modified_count)
        if main_id in admin_names:
            org_result = await database.organizations.update_many(
                {"main_id": main_id, "org_name": {"$ne": fields["org_name"]}},
                {"$set": {"org_name": fields["org_name"]}},
            )
            repaired += int(org_result.modified_count)
    return repaired
