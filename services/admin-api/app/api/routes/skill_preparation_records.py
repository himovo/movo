"""Tenant-scoped administrative access to Skill image preparation records."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_admin_user
from app.core.db import get_db
from app.services.skill_build_records import get_record, list_records
from app.system_audit.constants import MODULE_LABELS
from app.system_audit.repository import SystemAuditRepository


router = APIRouter()


async def _skill_build_digests(skill_id: str, current_user: dict) -> list[str]:
    row = await get_db().skills.find_one({
        "_id": skill_id, "main_id": str(current_user.get("main_id") or "default"), "deleted_at": None,
    }, {"package_digest": 1, "pending_package": 1})
    if not row:
        raise HTTPException(status_code=404, detail="skill_not_found")
    values = [str((row.get("pending_package") or {}).get("digest") or ""), str(row.get("package_digest") or "")]
    return list(dict.fromkeys(value for value in values if value))


@router.get("/{skill_id}/dependency-records")
async def skill_dependency_records(skill_id: str, current_user: dict = Depends(get_current_admin_user)) -> dict:
    digests = await _skill_build_digests(skill_id, current_user)
    groups = await asyncio.gather(*(asyncio.to_thread(list_records, digest) for digest in digests))
    items = [record for group in groups for record in group]
    return {"items": sorted(items, key=lambda item: item.get("startedAt", ""), reverse=True)[:20]}


@router.get("/{skill_id}/dependency-records/{record_id}")
async def skill_dependency_record(skill_id: str, record_id: str, current_user: dict = Depends(get_current_admin_user)) -> dict:
    for digest in await _skill_build_digests(skill_id, current_user):
        try:
            record = await asyncio.to_thread(get_record, digest, record_id)
        except HTTPException as exc:
            if exc.status_code == 404:
                continue
            raise
        try:
            await SystemAuditRepository().record_management_operation({
                "main_id": str(current_user.get("main_id") or "default"),
                "actor": str(current_user.get("username") or ""),
                "category": "management", "module": "skills", "module_label": MODULE_LABELS["skills"],
                "action": "view_preparation_log", "method": "GET",
                "route": "/api/skills/{skill_id}/dependency-records/{record_id}",
                "target": skill_id, "result": "success", "status_code": 200,
                "preparation_id": record_id,
            })
        except Exception:
            pass
        return record
    raise HTTPException(status_code=404, detail="preparation_record_not_found")
