from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import Response

from app.api.audit_messages import localize_audit_page
from app.api.deps import get_current_admin_user
from app.system_audit.query import SystemAuditQuery
from app.system_audit.export import export_audit, MIME_TYPE

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
    accept_language: str | None = Header(default=None),
    category: str = Query(default="management", pattern=r"^(management|agent|legacy)$"),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    keyword: str = Query(default="", max_length=200),
    result: str = Query(default="", pattern=r"^(|success|failed)$"),
    module: str = Query(default="", max_length=100),
) -> dict[str, Any]:
    page_data = await SystemAuditQuery().list_logs(
        main_id=_main_id(current_user), category=category, page=page, page_size=pageSize,
        keyword=keyword, result=result, module=module,
    )
    return localize_audit_page(page_data, accept_language)


@router.get("/export")
async def audit_export(
    current_user: dict = Depends(get_current_admin_user),
    accept_language: str | None = Header(default=None),
    category: str = Query(default="management", pattern=r"^(management|agent|legacy)$"),
    keyword: str = Query(default="", max_length=200),
    result: str = Query(default="", pattern=r"^(|success|failed)$"),
    module: str = Query(default="", max_length=100),
):
    data = await export_audit(main_id=_main_id(current_user), category=category, keyword=keyword,
        result=result, module=module, language=accept_language)
    filename = "system-audit-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + ".xlsx"
    return Response(data, media_type=MIME_TYPE, headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})
