from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_admin_user
from app.system_audit.query import SystemAuditQuery

router = APIRouter()


def _main_id(user: dict[str, Any]) -> str:
    return str(user.get("main_id") or "default")


@router.get("/overview")
async def audit_overview(current_user: dict = Depends(get_current_admin_user)) -> dict[str, int]:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    return await SystemAuditQuery().overview(_main_id(current_user), since)


@router.get("/logs")
async def audit_logs(
    current_user: dict = Depends(get_current_admin_user),
    category: str = Query(default="management", pattern=r"^(management|agent|legacy)$"),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    keyword: str = Query(default="", max_length=200),
    result: str = Query(default="", pattern=r"^(|success|failed)$"),
    module: str = Query(default="", max_length=100),
) -> dict[str, Any]:
    return await SystemAuditQuery().list_logs(
        main_id=_main_id(current_user), category=category, page=page, page_size=pageSize,
        keyword=keyword, result=result, module=module,
    )
