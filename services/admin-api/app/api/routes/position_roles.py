from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_current_admin_user
from app.core.db import get_db
from app.position_roles.constants import AGENT_CAPABILITY_KEYS, MIGRATION_COLLECTION, POSITION_ROLE_COLLECTION, USER_OVERRIDE_COLLECTION, USER_ROLE_COLLECTION
from app.position_roles.service import PositionRoleService
from app.position_roles.repository import utcnow
from app.services.organization_tools import organization_tool_query

router = APIRouter()


class PositionRolePayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    status: str = Field(default="active", pattern=r"^(active|disabled)$")
    capabilities: dict[str, bool] = Field(default_factory=dict)
    toolAccessMode: str = Field(default="selected", pattern=r"^(all|selected)$")
    toolIds: list[str] = Field(default_factory=list)
    skillAccessMode: str = Field(default="selected", pattern=r"^(all|selected)$")
    skillIds: list[str] = Field(default_factory=list)


class RoleCopyPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class RoleStatusPayload(BaseModel):
    enabled: bool


class UserRoleAssignmentPayload(BaseModel):
    primaryRoleId: str = Field(min_length=1)
    roleIds: list[str] = Field(min_length=1)


class BulkRoleAssignmentPayload(BaseModel):
    userIds: list[str] = Field(min_length=1)
    primaryRoleId: str = Field(min_length=1)
    roleIds: list[str] = Field(min_length=1)


class CapabilityOverridePayload(BaseModel):
    allowCapabilities: list[str] = Field(default_factory=list)
    denyCapabilities: list[str] = Field(default_factory=list)
    allowToolIds: list[str] = Field(default_factory=list)
    denyToolIds: list[str] = Field(default_factory=list)
    allowSkillIds: list[str] = Field(default_factory=list)
    denySkillIds: list[str] = Field(default_factory=list)
    effectiveAt: datetime | None = None
    expiresAt: datetime | None = None
    reason: str = Field(min_length=1, max_length=1000)


def _aware_utc(value: datetime | None, fallback: datetime | None = None) -> datetime | None:
    resolved = value if value is not None else fallback
    if resolved is None:
        return None
    if resolved.tzinfo is None:
        return resolved.replace(tzinfo=timezone.utc)
    return resolved.astimezone(timezone.utc)


def _main_id(user: dict[str, Any]) -> str:
    return str(user.get("main_id") or "default")


def _actor(user: dict[str, Any]) -> str:
    return str(user.get("username") or user.get("_id") or "admin")


@router.get("")
async def list_roles(current_user: dict = Depends(get_current_admin_user)) -> list[dict[str, Any]]:
    return await PositionRoleService().list_roles(_main_id(current_user))


@router.post("", status_code=201)
async def create_role(payload: PositionRolePayload, current_user: dict = Depends(get_current_admin_user)) -> dict[str, Any]:
    return await PositionRoleService().create_role(_main_id(current_user), payload.model_dump(), _actor(current_user))


@router.put("/{role_id}")
async def update_role(role_id: str, payload: PositionRolePayload, current_user: dict = Depends(get_current_admin_user)) -> dict[str, Any]:
    return await PositionRoleService().update_role(_main_id(current_user), role_id, payload.model_dump(), _actor(current_user))


@router.post("/{role_id}/copy", status_code=201)
async def copy_role(role_id: str, payload: RoleCopyPayload, current_user: dict = Depends(get_current_admin_user)) -> dict[str, Any]:
    return await PositionRoleService().copy_role(_main_id(current_user), role_id, payload.name, _actor(current_user))


@router.patch("/{role_id}/status")
async def update_role_status(role_id: str, payload: RoleStatusPayload, current_user: dict = Depends(get_current_admin_user)) -> dict[str, bool]:
    await PositionRoleService().set_status(_main_id(current_user), role_id, payload.enabled, _actor(current_user))
    return {"success": True}


@router.delete("/{role_id}")
async def delete_role(role_id: str, current_user: dict = Depends(get_current_admin_user)) -> dict[str, bool]:
    await PositionRoleService().delete_role(_main_id(current_user), role_id, _actor(current_user))
    return {"success": True}


@router.get("/catalog/resources")
async def resource_catalog(current_user: dict = Depends(get_current_admin_user)) -> dict[str, Any]:
    main_id = _main_id(current_user)
    db = get_db()
    tools = await db.external_tools.find(organization_tool_query(main_id, status="active")).sort("name", 1).to_list(length=5000)
    skills = await db.skills.find({"main_id": main_id, "enabled": True}).sort("name", 1).to_list(length=5000)
    return {
        "tools": [{"id": str(row.get("_id")), "name": row.get("name", ""), "type": row.get("type", "http")} for row in tools],
        "skills": [{"id": str(row.get("_id")), "name": row.get("name", ""), "type": row.get("type", "")} for row in skills],
    }


@router.get("/assignments/pending")
async def pending_assignments(current_user: dict = Depends(get_current_admin_user)) -> dict[str, Any]:
    main_id = _main_id(current_user)
    db = get_db()
    assigned = await db[USER_ROLE_COLLECTION].distinct("user_id", {"main_id": main_id})
    query: dict[str, Any] = {"main_id": main_id, "status": {"$ne": "deleted"}}
    if assigned:
        from bson import ObjectId
        query["_id"] = {"$nin": [ObjectId(item) for item in assigned if ObjectId.is_valid(item)]}
    rows = await db.end_users.find(query).sort("updated_at", -1).to_list(length=5000)
    migration = await db[MIGRATION_COLLECTION].find_one({"main_id": main_id})
    return {
        "count": len(rows),
        "migrationStatus": str((migration or {}).get("status") or "pending"),
        "users": [{"id": str(row.get("_id")), "name": row.get("name", ""), "loginName": row.get("login_name", "")} for row in rows],
    }


@router.post("/assignments/migration/complete")
async def complete_assignment_migration(current_user: dict = Depends(get_current_admin_user)) -> dict[str, bool]:
    main_id = _main_id(current_user)
    db = get_db()
    assigned = await db[USER_ROLE_COLLECTION].distinct("user_id", {"main_id": main_id})
    query: dict[str, Any] = {"main_id": main_id, "status": {"$ne": "deleted"}}
    if assigned:
        from bson import ObjectId
        query["_id"] = {"$nin": [ObjectId(item) for item in assigned if ObjectId.is_valid(item)]}
    pending_count = await db.end_users.count_documents(query)
    if pending_count:
        raise HTTPException(status_code=409, detail=f"仍有 {pending_count} 名员工未分配岗位角色")
    repository = PositionRoleService().repository
    await repository.complete_migration(main_id, _actor(current_user))
    await repository.audit(main_id, _actor(current_user), "complete_migration", "position_role_migration", main_id, {})
    return {"success": True}


@router.put("/assignments/users/{user_id}")
async def assign_user_roles(user_id: str, payload: UserRoleAssignmentPayload, current_user: dict = Depends(get_current_admin_user)) -> dict[str, bool]:
    service = PositionRoleService()
    main_id = _main_id(current_user)
    await service.validate_roles(main_id, payload.roleIds, payload.primaryRoleId)
    await service.repository.replace_user_roles(main_id, user_id, payload.roleIds, payload.primaryRoleId, actor=_actor(current_user))
    await service.repository.audit(main_id, _actor(current_user), "assign", "employee_position_roles", user_id, payload.model_dump())
    return {"success": True}


@router.post("/assignments/bulk")
async def bulk_assign_roles(payload: BulkRoleAssignmentPayload, current_user: dict = Depends(get_current_admin_user)) -> dict[str, int]:
    service = PositionRoleService()
    main_id = _main_id(current_user)
    await service.validate_roles(main_id, payload.roleIds, payload.primaryRoleId)
    for user_id in dict.fromkeys(payload.userIds):
        await service.repository.replace_user_roles(main_id, user_id, payload.roleIds, payload.primaryRoleId, actor=_actor(current_user))
    await service.repository.audit(main_id, _actor(current_user), "bulk_assign", "employee_position_roles", "bulk", payload.model_dump())
    return {"updated": len(set(payload.userIds))}


@router.post("/assignments/users/{user_id}/overrides", status_code=201)
async def create_override(user_id: str, payload: CapabilityOverridePayload, current_user: dict = Depends(get_current_admin_user)) -> dict[str, str]:
    main_id = _main_id(current_user)
    now = utcnow()
    effective_at = _aware_utc(payload.effectiveAt, now)
    expires_at = _aware_utc(payload.expiresAt)
    if expires_at is not None and expires_at <= effective_at:
        raise HTTPException(status_code=400, detail="失效时间必须晚于生效时间")
    unknown_capabilities = (set(payload.allowCapabilities) | set(payload.denyCapabilities)) - set(AGENT_CAPABILITY_KEYS)
    if unknown_capabilities:
        raise HTTPException(status_code=400, detail="包含未知的 Agent 能力")
    if set(payload.allowCapabilities) & set(payload.denyCapabilities):
        raise HTTPException(status_code=400, detail="同一能力不能同时允许和禁止")
    await PositionRoleService().validate_resource_ids(
        main_id,
        list(dict.fromkeys(payload.allowToolIds + payload.denyToolIds)),
        list(dict.fromkeys(payload.allowSkillIds + payload.denySkillIds)),
    )
    import uuid
    override_id = uuid.uuid4().hex
    doc = {
        "_id": override_id,
        "main_id": main_id,
        "user_id": user_id,
        "status": "active",
        "allow_capabilities": payload.allowCapabilities,
        "deny_capabilities": payload.denyCapabilities,
        "allow_tool_ids": payload.allowToolIds,
        "deny_tool_ids": payload.denyToolIds,
        "allow_skill_ids": payload.allowSkillIds,
        "deny_skill_ids": payload.denySkillIds,
        "effective_at": effective_at,
        "expires_at": expires_at,
        "reason": payload.reason,
        "created_by": _actor(current_user),
        "created_at": now,
        "updated_at": now,
    }
    db = get_db()
    await db[USER_OVERRIDE_COLLECTION].insert_one(doc)
    await PositionRoleService().repository.audit(main_id, _actor(current_user), "grant_override", "employee", user_id, {**payload.model_dump(mode="json"), "overrideId": override_id})
    return {"id": override_id}


@router.get("/assignments/users/{user_id}/overrides")
async def list_user_overrides(user_id: str, current_user: dict = Depends(get_current_admin_user)) -> list[dict[str, Any]]:
    main_id = _main_id(current_user)
    rows = await get_db()[USER_OVERRIDE_COLLECTION].find({"main_id": main_id, "user_id": user_id}).sort("created_at", -1).to_list(length=500)
    now = utcnow()
    return [{
        "id": str(row.get("_id") or ""),
        "status": "expired" if str(row.get("status") or "active") == "active" and row.get("expires_at") and _aware_utc(row.get("expires_at")) <= now else str(row.get("status") or "active"),
        "allowCapabilities": list(row.get("allow_capabilities") or []),
        "denyCapabilities": list(row.get("deny_capabilities") or []),
        "allowToolIds": list(row.get("allow_tool_ids") or []),
        "denyToolIds": list(row.get("deny_tool_ids") or []),
        "allowSkillIds": list(row.get("allow_skill_ids") or []),
        "denySkillIds": list(row.get("deny_skill_ids") or []),
        "effectiveAt": row.get("effective_at").isoformat() if row.get("effective_at") else "",
        "expiresAt": row.get("expires_at").isoformat() if row.get("expires_at") else "",
        "reason": str(row.get("reason") or ""),
        "createdBy": str(row.get("created_by") or ""),
        "createdAt": row.get("created_at").isoformat() if row.get("created_at") else "",
    } for row in rows]


@router.delete("/assignments/overrides/{override_id}")
async def revoke_override(override_id: str, current_user: dict = Depends(get_current_admin_user)) -> dict[str, bool]:
    main_id = _main_id(current_user)
    db = get_db()
    result = await db[USER_OVERRIDE_COLLECTION].update_one(
        {"_id": override_id, "main_id": main_id},
        {"$set": {"status": "revoked", "revoked_at": utcnow(), "updated_at": utcnow(), "revoked_by": _actor(current_user)}},
    )
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="特殊授权不存在")
    await PositionRoleService().repository.audit(main_id, _actor(current_user), "revoke_override", "capability_override", override_id, {})
    return {"success": True}
