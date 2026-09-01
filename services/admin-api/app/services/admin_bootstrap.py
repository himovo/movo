from __future__ import annotations

from app.core.config import settings
from app.repositories.org_user_repository import (
    ensure_indexes as ensure_org_user_indexes,
    ensure_bootstrap_account,
    ensure_group_exists,
)
from app.repositories.admin_session_repository import ensure_indexes as ensure_session_indexes
from app.repositories.setup_repository import get_setup_state


async def bootstrap_admin_user() -> None:
    await ensure_session_indexes()
    await ensure_org_user_indexes()
    
    if settings.bootstrap_admin_enabled:
        setup_state = await get_setup_state()
        main_id = str((setup_state or {}).get("main_id") or "").strip() or settings.bootstrap_main_id
        org_name = str((setup_state or {}).get("org_name") or "").strip() or settings.bootstrap_admin_org_name
        
        await ensure_group_exists(
            name="系统管理员",
            code="system_admin",
            main_id=main_id,
            description="系统内置账号组",
        )
        await ensure_bootstrap_account(
            main_id=main_id,
            username=settings.bootstrap_admin_username,
            password=settings.bootstrap_admin_password,
            display_name=settings.bootstrap_admin_display_name,
            role_name=settings.bootstrap_admin_role_name,
            org_name=org_name,
            group_code="system_admin",
        )

