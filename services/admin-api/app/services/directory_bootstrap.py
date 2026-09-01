from __future__ import annotations

from app.repositories.directory_repository import ensure_indexes
from app.core.db import get_db
from app.position_roles.repository import PositionRoleRepository
from app.services.employee_tenant_identity import repair_employee_tenant_identities


async def bootstrap_directory() -> None:
    await ensure_indexes()
    repository = PositionRoleRepository()
    await repository.ensure_indexes()
    db = get_db()
    await repair_employee_tenant_identities(db)
    tenant_ids = await db.admin_accounts.distinct("main_id", {"main_id": {"$nin": [None, "", "default"]}})
    for main_id in tenant_ids:
        role = await repository.ensure_full_access_role(str(main_id))
        setup = await db.system_bootstrap.find_one({"main_id": str(main_id)})
        employee_login = str((setup or {}).get("employee_username") or "")
        if employee_login:
            employee = await db.end_users.find_one({"main_id": str(main_id), "login_name": employee_login})
            if employee:
                await repository.assign_role(str(main_id), str(employee["_id"]), str(role["_id"]), primary=True, actor="system-bootstrap")
