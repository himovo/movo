from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.api.deps import get_current_admin_user
from app.api.time_utils import utc_iso
from app.core.config import settings
from app.core.db import get_db
from app.core.product_edition import assert_member_capacity
from app.core.quota_policy import USER_QUOTA_OVERRIDE_COLLECTION, USER_QUOTA_POLICY_COLLECTION
from app.core.security import hash_password
from app.repositories.directory_repository import (
    AUDIT_LOG_COLLECTION,
    DEPARTMENT_COLLECTION,
    USER_COLLECTION,
    USER_FIELD_DEF_COLLECTION,
    USER_FIELD_VALUE_COLLECTION,
    USER_IDENTITY_COLLECTION,
    USER_INVITE_COLLECTION,
    USER_ORG_REL_COLLECTION,
    ensure_indexes as ensure_directory_indexes,
)
from app.position_roles.constants import POSITION_ROLE_COLLECTION, USER_ROLE_COLLECTION
from app.position_roles.service import PositionRoleService
from app.services.employee_credentials import normalize_employee_credentials, redact_credential_payload
from app.services.employee_tenant_identity import employee_tenant_fields

router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_login_name_duplicate(error: DuplicateKeyError) -> bool:
    return "login_name" in str(error) or "user_main_login_name_unique" in str(error)


def _safe_oid(value: str, detail: str) -> ObjectId:
    try:
        return ObjectId(value)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc


def _main_id(current_user: dict) -> str:
    return str(current_user.get("main_id", "default"))


def _fmt_time(value: datetime | None) -> str:
    return utc_iso(value)


async def _write_audit(main_id: str, operator: str, action: str, target_type: str, target_id: str, payload: dict[str, Any]) -> None:
    db = get_db()
    await db[AUDIT_LOG_COLLECTION].insert_one(
        {
            "main_id": main_id,
            "operator": operator,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "payload": payload,
            "created_at": _now(),
        }
    )


async def _all_departments(main_id: str) -> list[dict]:
    db = get_db()
    cursor = db[DEPARTMENT_COLLECTION].find({"main_id": main_id}).sort("created_at", 1)
    return await cursor.to_list(length=5000)


def _dept_tree(rows: list[dict], user_count_map: dict[str, int]) -> list[dict[str, Any]]:
    node_map: dict[str, dict[str, Any]] = {}
    roots: list[dict[str, Any]] = []
    for row in rows:
        node_id = str(row["_id"])
        node_map[node_id] = {
            "id": node_id,
            "name": row.get("name", ""),
            "code": row.get("code", ""),
            "status": row.get("status", "active"),
            "parentId": row.get("parent_id"),
            "userCount": user_count_map.get(node_id, 0),
            "children": [],
        }
    for node in node_map.values():
        parent_id = node.get("parentId")
        if parent_id and parent_id in node_map:
            node_map[parent_id]["children"].append(node)
        else:
            roots.append(node)
    return roots


def _build_dept_path(parent: dict | None, dept_name: str) -> tuple[list[str], list[str]]:
    if parent is None:
        return [], []
    return [*parent.get("path_ids", []), str(parent["_id"])], [*parent.get("path_names", []), parent.get("name", "")]


async def _update_descendant_paths(
    main_id: str,
    moved_id: str,
    moved_name: str,
    old_path_ids: list[str],
    old_path_names: list[str],
    new_path_ids: list[str],
    new_path_names: list[str],
) -> None:
    db = get_db()
    cursor = db[DEPARTMENT_COLLECTION].find({"main_id": main_id, "path_ids": moved_id})
    descendants = await cursor.to_list(length=5000)
    for doc in descendants:
        path_ids = doc.get("path_ids", [])
        path_names = doc.get("path_names", [])
        if moved_id not in path_ids:
            continue
        idx = path_ids.index(moved_id)
        suffix_ids = path_ids[idx + 1 :]
        suffix_names = path_names[idx + 1 :]
        next_ids = [*new_path_ids, moved_id, *suffix_ids]
        next_names = [*new_path_names, moved_name, *suffix_names]
        await db[DEPARTMENT_COLLECTION].update_one(
            {"_id": doc["_id"]},
            {"$set": {"path_ids": next_ids, "path_names": next_names, "updated_at": _now()}},
        )


class DepartmentCreatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    parentId: str | None = None
    status: str = Field(default="active", pattern=r"^(active|disabled)$")


class DepartmentUpdatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    status: str = Field(default="active", pattern=r"^(active|disabled)$")


class DepartmentMovePayload(BaseModel):
    parentId: str | None = None


class UserCreatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    mobile: str = Field(min_length=1, max_length=32)
    email: str = Field(min_length=1, max_length=128)
    status: str = Field(default="active", pattern=r"^(active|disabled)$")
    source: str = Field(default="local", pattern=r"^(local|dingtalk|wecom|feishu)$")
    sourceUserId: str = Field(default="", max_length=128)
    primaryDepartmentId: str = Field(min_length=1)
    departmentIds: list[str] = Field(default_factory=list)
    loginName: str = Field(default="", max_length=64)
    initialPassword: str = Field(default="", max_length=128)
    primaryRoleId: str = Field(min_length=1)
    roleIds: list[str] = Field(min_length=1)


class UserUpdatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    mobile: str = Field(min_length=1, max_length=32)
    email: str = Field(min_length=1, max_length=128)
    status: str = Field(default="active", pattern=r"^(active|disabled)$")
    source: str = Field(default="local", pattern=r"^(local|dingtalk|wecom|feishu)$")
    sourceUserId: str = Field(default="", max_length=128)
    primaryDepartmentId: str = Field(min_length=1)
    departmentIds: list[str] = Field(default_factory=list)
    loginName: str = Field(default="", max_length=64)
    resetPassword: str = Field(default="", max_length=128)
    primaryRoleId: str = Field(min_length=1)
    roleIds: list[str] = Field(min_length=1)


class UserFieldDefPayload(BaseModel):
    fieldKey: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_]+$")
    label: str = Field(min_length=1, max_length=64)
    fieldType: str = Field(pattern=r"^(text|textarea|select|multiselect)$")
    required: bool = False
    options: list[str] = Field(default_factory=list)
    rows: int = Field(default=3, ge=2, le=12)
    masked: bool = False
    enabled: bool = True
    sort: int = 0


class UserCustomValuesPayload(BaseModel):
    values: dict[str, Any]


class UserIdentityPayload(BaseModel):
    provider: str = Field(pattern=r"^(dingtalk|wecom|feishu)$")
    providerUserId: str = Field(min_length=1, max_length=128)
    unionId: str = Field(default="", max_length=128)
    corpId: str = Field(default="", max_length=128)
    tenantKey: str = Field(default="", max_length=128)
    isPrimary: bool = False
    bindStatus: str = Field(default="bound", pattern=r"^(bound|pending|conflict)$")


class OrgInviteCreatePayload(BaseModel):
    defaultDepartmentId: str | None = None
    expiresHours: int | None = Field(default=None, ge=1, le=24 * 30)
    primaryRoleId: str = Field(min_length=1)
    roleIds: list[str] = Field(min_length=1)


class InviteAcceptPayload(BaseModel):
    name: str = Field(default="", max_length=64)
    mobile: str = Field(default="", max_length=32)
    email: str = Field(default="", max_length=128)
    loginName: str = Field(default="", max_length=64)
    password: str = Field(min_length=6, max_length=128)


@router.get("/departments/tree")
async def get_department_tree(current_user: dict = Depends(get_current_admin_user)) -> list[dict[str, Any]]:
    main_id = _main_id(current_user)
    db = get_db()
    departments = await _all_departments(main_id)
    rel_rows = await db[USER_ORG_REL_COLLECTION].find({"main_id": main_id}).to_list(length=20000)
    dept_scope_map = {
        str(department.get("_id")): {
            str(department.get("_id")),
            *(str(row.get("_id")) for row in departments if str(department.get("_id")) in (row.get("path_ids") or [])),
        }
        for department in departments
    }
    user_ids_by_dept: dict[str, set[str]] = {dept_id: set() for dept_id in dept_scope_map}
    for rel in rel_rows:
        org_id = str(rel.get("org_id", ""))
        user_id = str(rel.get("user_id") or "")
        if not org_id or not user_id:
            continue
        for dept_id, scoped_dept_ids in dept_scope_map.items():
            if org_id in scoped_dept_ids:
                user_ids_by_dept.setdefault(dept_id, set()).add(user_id)
    user_count_map = {dept_id: len(user_ids) for dept_id, user_ids in user_ids_by_dept.items()}
    return _dept_tree(departments, user_count_map)


@router.post("/departments", status_code=status.HTTP_201_CREATED)
async def create_department(payload: DepartmentCreatePayload, current_user: dict = Depends(get_current_admin_user)) -> dict[str, Any]:
    main_id = _main_id(current_user)
    db = get_db()
    parent = None
    if payload.parentId:
        parent = await db[DEPARTMENT_COLLECTION].find_one({"_id": _safe_oid(payload.parentId, "父部门ID无效"), "main_id": main_id})
        if parent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="父部门不存在")
    path_ids, path_names = _build_dept_path(parent, payload.name)
    code_base = payload.name.strip().lower().replace(" ", "_")
    code = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in code_base).strip("_") or "dept"
    suffix = 1
    while await db[DEPARTMENT_COLLECTION].find_one({"main_id": main_id, "code": code}):
        suffix += 1
        code = f"{code_base}_{suffix}"
    now = _now()
    result = await db[DEPARTMENT_COLLECTION].insert_one(
        {
            "main_id": main_id,
            "name": payload.name.strip(),
            "code": code,
            "parent_id": str(parent["_id"]) if parent else None,
            "path_ids": path_ids,
            "path_names": path_names,
            "status": payload.status,
            "source": "local",
            "source_dept_id": "",
            "created_at": now,
            "updated_at": now,
        }
    )
    created = await db[DEPARTMENT_COLLECTION].find_one({"_id": result.inserted_id})
    await _write_audit(main_id, str(current_user.get("username", "")), "create", "department", str(result.inserted_id), payload.model_dump())
    return {
        "id": str(created["_id"]),
        "name": created.get("name", ""),
        "code": created.get("code", ""),
        "parentId": created.get("parent_id"),
        "status": created.get("status", "active"),
    }


@router.put("/departments/{department_id}")
async def update_department(
    department_id: str,
    payload: DepartmentUpdatePayload,
    current_user: dict = Depends(get_current_admin_user),
) -> dict[str, Any]:
    main_id = _main_id(current_user)
    db = get_db()
    dep_oid = _safe_oid(department_id, "部门ID无效")
    existing = await db[DEPARTMENT_COLLECTION].find_one({"_id": dep_oid, "main_id": main_id})
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部门不存在")
    old_name = existing.get("name", "")
    updated = await db[DEPARTMENT_COLLECTION].find_one_and_update(
        {"_id": dep_oid, "main_id": main_id},
        {"$set": {"name": payload.name.strip(), "status": payload.status, "updated_at": _now()}},
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部门不存在")
    if old_name != payload.name.strip():
        prefix = [*existing.get("path_names", []), old_name]
        cursor = db[DEPARTMENT_COLLECTION].find({"main_id": main_id, "path_ids": department_id})
        descendants = await cursor.to_list(length=5000)
        for row in descendants:
            names = row.get("path_names", [])
            if len(names) >= len(prefix) and names[: len(prefix)] == prefix:
                new_names = [*existing.get("path_names", []), payload.name.strip(), *names[len(prefix) :]]
                await db[DEPARTMENT_COLLECTION].update_one(
                    {"_id": row["_id"]},
                    {"$set": {"path_names": new_names, "updated_at": _now()}},
                )
    await _write_audit(main_id, str(current_user.get("username", "")), "update", "department", department_id, payload.model_dump())
    return {"success": True}


@router.post("/departments/{department_id}/move")
async def move_department(
    department_id: str,
    payload: DepartmentMovePayload,
    current_user: dict = Depends(get_current_admin_user),
) -> dict[str, bool]:
    main_id = _main_id(current_user)
    db = get_db()
    dep_oid = _safe_oid(department_id, "部门ID无效")
    department = await db[DEPARTMENT_COLLECTION].find_one({"_id": dep_oid, "main_id": main_id})
    if department is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部门不存在")

    parent = None
    if payload.parentId:
        if payload.parentId == department_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能移动到自身或子部门下")
        parent = await db[DEPARTMENT_COLLECTION].find_one({"_id": _safe_oid(payload.parentId, "父部门ID无效"), "main_id": main_id})
        if parent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="父部门不存在")
        if department_id in parent.get("path_ids", []):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能移动到自身或子部门下")
    old_path_ids = department.get("path_ids", [])
    old_path_names = department.get("path_names", [])
    new_path_ids, new_path_names = _build_dept_path(parent, department.get("name", ""))
    await db[DEPARTMENT_COLLECTION].update_one(
        {"_id": dep_oid},
        {
            "$set": {
                "parent_id": str(parent["_id"]) if parent else None,
                "path_ids": new_path_ids,
                "path_names": new_path_names,
                "updated_at": _now(),
            }
        },
    )
    await _update_descendant_paths(
        main_id=main_id,
        moved_id=department_id,
        moved_name=department.get("name", ""),
        old_path_ids=old_path_ids,
        old_path_names=old_path_names,
        new_path_ids=new_path_ids,
        new_path_names=new_path_names,
    )
    await _write_audit(
        main_id,
        str(current_user.get("username", "")),
        "move",
        "department",
        department_id,
        {"parentId": payload.parentId},
    )
    return {"success": True}


@router.delete("/departments/{department_id}")
async def delete_department(department_id: str, current_user: dict = Depends(get_current_admin_user)) -> dict[str, bool]:
    main_id = _main_id(current_user)
    db = get_db()
    dep_oid = _safe_oid(department_id, "部门ID无效")
    existing = await db[DEPARTMENT_COLLECTION].find_one({"_id": dep_oid, "main_id": main_id})
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部门不存在")
    if existing.get("code") == "root":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="根部门不可删除")
    child_rows = await db[DEPARTMENT_COLLECTION].find(
        {"main_id": main_id, "$or": [{"parent_id": department_id}, {"path_ids": department_id}]},
        {"_id": 1},
    ).to_list(length=5000)
    child_ids = [str(row["_id"]) for row in child_rows]
    if child_ids:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="请先删除子部门")
    rel_count = await db[USER_ORG_REL_COLLECTION].count_documents({"main_id": main_id, "org_id": {"$in": [department_id, *child_ids]}})
    if rel_count > 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该部门下仍有用户")
    await db[DEPARTMENT_COLLECTION].delete_one({"_id": dep_oid, "main_id": main_id})
    await _write_audit(main_id, str(current_user.get("username", "")), "delete", "department", department_id, {"name": existing.get("name", "")})
    return {"success": True}


@router.get("/users")
async def list_users(
    current_user: dict = Depends(get_current_admin_user),
    departmentId: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    statusFilter: str | None = Query(default=None),
    sourceFilter: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    main_id = _main_id(current_user)
    db = get_db()
    query: dict[str, Any] = {"main_id": main_id}
    if statusFilter:
        query["status"] = statusFilter
    if sourceFilter:
        query["source"] = sourceFilter
    if keyword:
        regex = {"$regex": keyword.strip(), "$options": "i"}
        query["$or"] = [{"name": regex}, {"mobile": regex}, {"email": regex}, {"login_name": regex}]
    if departmentId:
        dept_filter_ids = [departmentId]
        child_rows = await db[DEPARTMENT_COLLECTION].find(
            {"main_id": main_id, "path_ids": departmentId},
            {"_id": 1},
        ).to_list(length=5000)
        dept_filter_ids.extend(str(row["_id"]) for row in child_rows)
        rel_rows = await db[USER_ORG_REL_COLLECTION].find({"main_id": main_id, "org_id": {"$in": dept_filter_ids}}).to_list(length=20000)
        user_ids = [row.get("user_id") for row in rel_rows]
        query["_id"] = {"$in": [ObjectId(uid) for uid in user_ids if ObjectId.is_valid(uid)]} if user_ids else {"$in": []}
    users = await db[USER_COLLECTION].find(query).sort("updated_at", -1).to_list(length=5000)
    deps = await db[DEPARTMENT_COLLECTION].find({"main_id": main_id}).to_list(length=5000)
    dep_map = {str(item["_id"]): item.get("name", "") for item in deps}
    rel_rows = await db[USER_ORG_REL_COLLECTION].find({"main_id": main_id}).to_list(length=20000)
    primary_map: dict[str, str] = {}
    for rel in rel_rows:
        if rel.get("is_primary"):
            primary_map[str(rel.get("user_id", ""))] = str(rel.get("org_id", ""))
    user_ids = [str(row["_id"]) for row in users]
    role_assignments = await db[USER_ROLE_COLLECTION].find({"main_id": main_id, "user_id": {"$in": user_ids}}).to_list(length=50000) if user_ids else []
    role_ids = list({str(row.get("role_id") or "") for row in role_assignments if row.get("role_id")})
    role_rows = await db[POSITION_ROLE_COLLECTION].find({"main_id": main_id, "_id": {"$in": role_ids}}).to_list(length=5000) if role_ids else []
    role_name_map = {str(row.get("_id")): str(row.get("name") or "") for row in role_rows}
    roles_by_user: dict[str, list[dict[str, Any]]] = {user_id: [] for user_id in user_ids}
    for assignment in role_assignments:
        assigned_role_id = str(assignment.get("role_id") or "")
        roles_by_user.setdefault(str(assignment.get("user_id") or ""), []).append({
            "id": assigned_role_id,
            "name": role_name_map.get(assigned_role_id, ""),
            "isPrimary": bool(assignment.get("is_primary")),
        })
    custom_value_map: dict[str, dict[str, Any]] = {user_id: {} for user_id in user_ids}
    if user_ids:
        value_rows = await db[USER_FIELD_VALUE_COLLECTION].find(
            {"main_id": main_id, "user_id": {"$in": user_ids}},
        ).to_list(length=50000)
        for value_row in value_rows:
            user_id = str(value_row.get("user_id") or "")
            field_key = str(value_row.get("field_key") or "")
            if user_id and field_key:
                custom_value_map.setdefault(user_id, {})[field_key] = value_row.get("value")
    return [
        {
            "id": str(row["_id"]),
            "name": row.get("name", ""),
            "mobile": row.get("mobile", ""),
            "email": row.get("email", ""),
            "status": row.get("status", "active"),
            "source": row.get("source", "local"),
            "sourceUserId": row.get("source_user_id", ""),
            "loginName": row.get("login_name", ""),
            "primaryDepartmentId": primary_map.get(str(row["_id"]), row.get("primary_org_id", "")),
            "primaryDepartmentName": dep_map.get(primary_map.get(str(row["_id"]), row.get("primary_org_id", "")), ""),
            "customFields": custom_value_map.get(str(row["_id"]), {}),
            "positionRoles": roles_by_user.get(str(row["_id"]), []),
            "pendingPositionRole": not bool(roles_by_user.get(str(row["_id"]), [])),
            "updatedAt": _fmt_time(row.get("updated_at")),
        }
        for row in users
    ]


async def _upsert_user_relations(main_id: str, user_id: str, primary_dept_id: str, department_ids: list[str]) -> None:
    db = get_db()
    unique_ids = list(dict.fromkeys([primary_dept_id, *department_ids]))
    await db[USER_ORG_REL_COLLECTION].delete_many({"main_id": main_id, "user_id": user_id})
    if not unique_ids:
        return
    rows = [
        {
            "main_id": main_id,
            "user_id": user_id,
            "org_id": dept_id,
            "is_primary": dept_id == primary_dept_id,
            "created_at": _now(),
            "updated_at": _now(),
        }
        for dept_id in unique_ids
    ]
    await db[USER_ORG_REL_COLLECTION].insert_many(rows)


async def _validate_departments(main_id: str, dept_ids: list[str]) -> None:
    db = get_db()
    for dept_id in dept_ids:
        dep = await db[DEPARTMENT_COLLECTION].find_one({"_id": _safe_oid(dept_id, "部门ID无效"), "main_id": main_id, "status": "active"})
        if dep is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="存在无效部门")


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreatePayload, current_user: dict = Depends(get_current_admin_user)) -> dict[str, Any]:
    main_id = _main_id(current_user)
    db = get_db()
    await assert_member_capacity(main_id)
    department_ids = payload.departmentIds or [payload.primaryDepartmentId]
    await _validate_departments(main_id, [payload.primaryDepartmentId, *department_ids])
    role_service = PositionRoleService()
    await role_service.validate_roles(main_id, payload.roleIds, payload.primaryRoleId)
    mobile = payload.mobile.strip()
    email = payload.email.strip()
    if not mobile:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请填写手机号")
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请填写邮箱")

    now = _now()
    try:
        login_name, initial_password = normalize_employee_credentials(
            source=payload.source,
            login_name=payload.loginName,
            password=payload.initialPassword,
            creating=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    user_doc: dict[str, Any] = {
        "main_id": main_id,
        **employee_tenant_fields(main_id, str(current_user.get("org_name") or "")),
        "name": payload.name.strip(),
        "mobile": mobile,
        "email": email,
        "status": payload.status,
        "source": payload.source,
        "source_user_id": payload.sourceUserId.strip(),
        "primary_org_id": payload.primaryDepartmentId,
        "created_at": now,
        "updated_at": now,
    }
    if login_name:
        user_doc["login_name"] = login_name
    if login_name and initial_password:
        password_hash, password_salt = hash_password(initial_password)
        user_doc["password_hash"] = password_hash
        user_doc["password_salt"] = password_salt
    try:
        result = await db[USER_COLLECTION].insert_one(user_doc)
    except DuplicateKeyError as exc:
        if not login_name and _is_login_name_duplicate(exc):
            await ensure_directory_indexes()
            try:
                result = await db[USER_COLLECTION].insert_one(user_doc)
            except DuplicateKeyError as retry_exc:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="登录名已存在") from retry_exc
        else:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="登录名已存在") from exc
    user_id = str(result.inserted_id)
    await _upsert_user_relations(main_id, user_id, payload.primaryDepartmentId, department_ids)
    await role_service.repository.replace_user_roles(main_id, user_id, payload.roleIds, payload.primaryRoleId, actor=str(current_user.get("username", "")))
    await role_service.repository.audit(
        main_id,
        str(current_user.get("username", "")),
        "assign",
        "employee_position_roles",
        user_id,
        {"primaryRoleId": payload.primaryRoleId, "roleIds": payload.roleIds},
    )
    await _write_audit(
        main_id,
        str(current_user.get("username", "")),
        "create",
        "user",
        user_id,
        redact_credential_payload(payload.model_dump()),
    )
    return {"id": user_id}


@router.put("/users/{user_id}")
async def update_user(user_id: str, payload: UserUpdatePayload, current_user: dict = Depends(get_current_admin_user)) -> dict[str, bool]:
    main_id = _main_id(current_user)
    db = get_db()
    user_oid = _safe_oid(user_id, "用户ID无效")
    existing = await db[USER_COLLECTION].find_one({"_id": user_oid, "main_id": main_id})
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    department_ids = payload.departmentIds or [payload.primaryDepartmentId]
    await _validate_departments(main_id, [payload.primaryDepartmentId, *department_ids])
    role_service = PositionRoleService()
    await role_service.validate_roles(main_id, payload.roleIds, payload.primaryRoleId)
    mobile = payload.mobile.strip()
    email = payload.email.strip()
    if not mobile:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请填写手机号")
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请填写邮箱")

    try:
        login_name, reset_password = normalize_employee_credentials(
            source=payload.source,
            login_name=payload.loginName,
            password=payload.resetPassword,
            creating=False,
            has_existing_password=bool(existing.get("password_hash") and existing.get("password_salt")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    update_doc: dict[str, Any] = {
        "name": payload.name.strip(),
        "mobile": mobile,
        "email": email,
        "status": payload.status,
        "source": payload.source,
        "source_user_id": payload.sourceUserId.strip(),
        "primary_org_id": payload.primaryDepartmentId,
        "updated_at": _now(),
    }
    update_ops: dict[str, Any] = {"$set": update_doc}
    if login_name:
        update_doc["login_name"] = login_name
    else:
        update_ops["$unset"] = {"login_name": "", "password_hash": "", "password_salt": ""}
    if reset_password:
        password_hash, password_salt = hash_password(reset_password)
        update_doc["password_hash"] = password_hash
        update_doc["password_salt"] = password_salt
    try:
        await db[USER_COLLECTION].update_one({"_id": user_oid, "main_id": main_id}, update_ops)
    except DuplicateKeyError as exc:
        if not login_name and _is_login_name_duplicate(exc):
            await ensure_directory_indexes()
            try:
                await db[USER_COLLECTION].update_one({"_id": user_oid, "main_id": main_id}, update_ops)
            except DuplicateKeyError as retry_exc:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="登录名已存在") from retry_exc
        else:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="登录名已存在") from exc
    await _upsert_user_relations(main_id, user_id, payload.primaryDepartmentId, department_ids)
    await role_service.repository.replace_user_roles(main_id, user_id, payload.roleIds, payload.primaryRoleId, actor=str(current_user.get("username", "")))
    await role_service.repository.audit(
        main_id,
        str(current_user.get("username", "")),
        "assign",
        "employee_position_roles",
        user_id,
        {"primaryRoleId": payload.primaryRoleId, "roleIds": payload.roleIds},
    )
    await _write_audit(
        main_id,
        str(current_user.get("username", "")),
        "update",
        "user",
        user_id,
        redact_credential_payload(payload.model_dump()),
    )
    return {"success": True}


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, current_user: dict = Depends(get_current_admin_user)) -> dict[str, bool]:
    main_id = _main_id(current_user)
    db = get_db()
    user_oid = _safe_oid(user_id, "用户ID无效")
    exists = await db[USER_COLLECTION].find_one({"_id": user_oid, "main_id": main_id})
    if exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    await db[USER_COLLECTION].delete_one({"_id": user_oid, "main_id": main_id})
    await db[USER_ORG_REL_COLLECTION].delete_many({"main_id": main_id, "user_id": user_id})
    await db[USER_FIELD_VALUE_COLLECTION].delete_many({"main_id": main_id, "user_id": user_id})
    await db[USER_IDENTITY_COLLECTION].delete_many({"main_id": main_id, "user_id": user_id})
    await db[USER_ROLE_COLLECTION].delete_many({"main_id": main_id, "user_id": user_id})
    await db[USER_QUOTA_POLICY_COLLECTION].delete_many({"main_id": main_id, "scope_type": "user", "scope_id": user_id})
    await db[USER_QUOTA_OVERRIDE_COLLECTION].delete_many({"main_id": main_id, "user_id": user_id})
    await _write_audit(main_id, str(current_user.get("username", "")), "delete", "user", user_id, {"name": exists.get("name", "")})
    return {"success": True}


@router.post("/users/{user_id}/disable")
async def disable_user(user_id: str, current_user: dict = Depends(get_current_admin_user)) -> dict[str, bool]:
    main_id = _main_id(current_user)
    db = get_db()
    user_oid = _safe_oid(user_id, "用户ID无效")
    exists = await db[USER_COLLECTION].find_one({"_id": user_oid, "main_id": main_id})
    if exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    await db[USER_COLLECTION].update_one({"_id": user_oid, "main_id": main_id}, {"$set": {"status": "disabled", "updated_at": _now()}})
    await _write_audit(main_id, str(current_user.get("username", "")), "disable", "user", user_id, {})
    return {"success": True}


@router.post("/users/{user_id}/enable")
async def enable_user(user_id: str, current_user: dict = Depends(get_current_admin_user)) -> dict[str, bool]:
    main_id = _main_id(current_user)
    db = get_db()
    user_oid = _safe_oid(user_id, "用户ID无效")
    exists = await db[USER_COLLECTION].find_one({"_id": user_oid, "main_id": main_id})
    if exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    await db[USER_COLLECTION].update_one({"_id": user_oid}, {"$set": {"status": "active", "updated_at": _now()}})
    await _write_audit(main_id, str(current_user.get("username", "")), "enable", "user", user_id, {})
    return {"success": True}


@router.post("/invites")
async def create_org_invite_link(
    payload: OrgInviteCreatePayload,
    current_user: dict = Depends(get_current_admin_user),
) -> dict[str, Any]:
    main_id = _main_id(current_user)
    if str(main_id).strip() == "default":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="当前管理员租户ID仍为 default，请先配置真实租户ID后再生成邀请链接",
        )
    db = get_db()
    role_service = PositionRoleService()
    await role_service.validate_roles(main_id, payload.roleIds, payload.primaryRoleId)
    default_department_id = payload.defaultDepartmentId or None
    if default_department_id:
        dep = await db[DEPARTMENT_COLLECTION].find_one(
            {"_id": _safe_oid(default_department_id, "部门ID无效"), "main_id": main_id, "status": "active"}
        )
        if dep is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="默认部门不存在或已停用")
    ttl_hours = payload.expiresHours or max(1, int(settings.invite_token_ttl_hours))
    expires_at = _now() + timedelta(hours=ttl_hours)
    token = secrets.token_urlsafe(32)
    invite_doc = {
        "main_id": main_id,
        "user_id": None,
        "token": token,
        "purpose": "register",
        "status": "active",
        "created_by": str(current_user.get("username", "")),
        "org_name": str(current_user.get("org_name") or "企业组织"),
        "created_at": _now(),
        "updated_at": _now(),
        "expires_at": expires_at,
        "used_at": None,
        "default_department_id": default_department_id,
        "primary_role_id": payload.primaryRoleId,
        "role_ids": payload.roleIds,
    }
    await db[USER_INVITE_COLLECTION].insert_one(invite_doc)
    portal_base = settings.user_portal_base_url.rstrip("/")
    invite_url = f"{portal_base}/?invite_code={token}&register=1"
    await _write_audit(
        main_id,
        str(current_user.get("username", "")),
        "create",
        "org_invite",
        token,
        {"expiresHours": ttl_hours, "defaultDepartmentId": default_department_id, "primaryRoleId": payload.primaryRoleId, "roleIds": payload.roleIds},
    )
    return {
        "inviteUrl": invite_url,
        "token": token,
        "purpose": "register",
        "expiresAt": _fmt_time(expires_at),
    }


async def _find_active_invite(token: str) -> dict[str, Any]:
    db = get_db()
    invite = await db[USER_INVITE_COLLECTION].find_one({"token": token, "status": "active"})
    if invite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="邀请链接不存在或已失效")
    expires_at = _as_utc(invite.get("expires_at"))
    if expires_at and expires_at < _now():
        await db[USER_INVITE_COLLECTION].update_one({"_id": invite["_id"]}, {"$set": {"status": "expired", "updated_at": _now()}})
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="邀请链接已过期")
    return invite


@router.get("/invite-links/{token}")
async def get_invite_link_detail(token: str) -> dict[str, Any]:
    db = get_db()
    invite = await _find_active_invite(token)
    user: dict[str, Any] | None = None
    raw_user_id = invite.get("user_id")
    if raw_user_id:
        user_oid = _safe_oid(str(raw_user_id), "邀请数据异常")
        user = await db[USER_COLLECTION].find_one({"_id": user_oid, "main_id": invite.get("main_id")})
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="邀请用户不存在")
    return {
        "purpose": invite.get("purpose", "register"),
        "expiresAt": _fmt_time(invite.get("expires_at")),
        "orgName": str(invite.get("org_name") or "企业组织"),
        "defaultDepartmentId": invite.get("default_department_id"),
        "primaryRoleId": invite.get("primary_role_id"),
        "roleIds": invite.get("role_ids") or [],
        "user": {
            "name": (user or {}).get("name", ""),
            "mobile": (user or {}).get("mobile", ""),
            "email": (user or {}).get("email", ""),
            "loginName": (user or {}).get("login_name", ""),
        },
    }


@router.post("/invite-links/{token}/accept")
async def accept_invite_link(token: str, payload: InviteAcceptPayload) -> dict[str, bool]:
    db = get_db()
    invite = await _find_active_invite(token)
    main_id = str(invite.get("main_id", "default"))
    if main_id == "default":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="邀请所属租户ID无效，请联系管理员重新生成邀请链接")
    role_service = PositionRoleService()
    invite_role_ids = [str(item) for item in invite.get("role_ids") or []]
    invite_primary_role_id = str(invite.get("primary_role_id") or "")
    await role_service.validate_roles(main_id, invite_role_ids, invite_primary_role_id)
    if invite.get("user_id"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前邀请策略仅支持新用户注册，请联系管理员重置密码")
    user_id = str(invite.get("user_id", "") or "")
    user: dict[str, Any] | None = None
    user_oid: ObjectId | None = None
    if user_id:
        user_oid = _safe_oid(user_id, "邀请数据异常")
        user = await db[USER_COLLECTION].find_one({"_id": user_oid, "main_id": main_id})
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="邀请用户不存在")

    purpose = str(invite.get("purpose", "register"))
    current_login = str((user or {}).get("login_name", "") or "").strip()
    next_login = payload.loginName.strip()
    if purpose == "register":
        if current_login:
            next_login = current_login
        elif not next_login:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请填写登录名")
    else:
        next_login = current_login or next_login
        if not next_login:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前用户未配置登录名")

    if next_login != current_login:
        duplicate = await db[USER_COLLECTION].find_one({"main_id": main_id, "login_name": next_login})
        if duplicate and str(duplicate["_id"]) != user_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="登录名已存在")

    password_hash, password_salt = hash_password(payload.password)
    if user is None:
        await assert_member_capacity(main_id)
        default_department_id = str(invite.get("default_department_id") or "")
        if default_department_id:
            dep = await db[DEPARTMENT_COLLECTION].find_one(
                {"_id": _safe_oid(default_department_id, "默认部门ID无效"), "main_id": main_id, "status": "active"}
            )
            if dep is None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="默认部门不存在或已停用，请联系管理员重发邀请")
            primary_department_id = default_department_id
        else:
            root_dep = await db[DEPARTMENT_COLLECTION].find_one({"main_id": main_id, "code": "root"})
            if root_dep is None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="企业部门初始化异常，请联系管理员")
            primary_department_id = str(root_dep["_id"])
        now = _now()
        create_doc = {
            "main_id": main_id,
            **employee_tenant_fields(main_id, str(invite.get("org_name") or "")),
            "name": payload.name.strip() or next_login,
            "mobile": payload.mobile.strip(),
            "email": payload.email.strip(),
            "status": "active",
            "source": "local",
            "source_user_id": "",
            "primary_org_id": primary_department_id,
            "login_name": next_login,
            "password_hash": password_hash,
            "password_salt": password_salt,
            "created_at": now,
            "updated_at": now,
        }
        try:
            result = await db[USER_COLLECTION].insert_one(create_doc)
        except DuplicateKeyError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="登录名已存在") from exc
        user_id = str(result.inserted_id)
        await _upsert_user_relations(main_id, user_id, primary_department_id, [primary_department_id])
    else:
        await db[USER_COLLECTION].update_one(
            {"_id": user_oid, "main_id": main_id},
            {
                "$set": {
                    "name": payload.name.strip() or user.get("name", ""),
                    "mobile": payload.mobile.strip() or user.get("mobile", ""),
                    "email": payload.email.strip() or user.get("email", ""),
                    "login_name": next_login,
                    "password_hash": password_hash,
                    "password_salt": password_salt,
                    "status": "active",
                    "updated_at": _now(),
                }
            },
        )
    await db[USER_INVITE_COLLECTION].update_one(
        {"_id": invite["_id"]},
        {"$set": {"status": "used", "used_at": _now(), "updated_at": _now()}},
    )
    await role_service.repository.replace_user_roles(main_id, user_id, invite_role_ids, invite_primary_role_id, actor="invite")
    await role_service.repository.audit(
        main_id,
        "invite",
        "assign",
        "employee_position_roles",
        user_id,
        {"primaryRoleId": invite_primary_role_id, "roleIds": invite_role_ids},
    )
    await _write_audit(
        main_id,
        "invite",
        "accept",
        "user_invite",
        user_id,
        {"purpose": purpose, "loginName": next_login},
    )
    return {"success": True}


@router.get("/user-fields")
async def list_user_fields(current_user: dict = Depends(get_current_admin_user)) -> list[dict[str, Any]]:
    main_id = _main_id(current_user)
    db = get_db()
    rows = await db[USER_FIELD_DEF_COLLECTION].find({"main_id": main_id}).sort("sort", 1).to_list(length=500)
    return [
        {
            "id": str(row["_id"]),
            "fieldKey": row.get("field_key", ""),
            "label": row.get("label", ""),
            "fieldType": row.get("field_type", "text"),
            "required": bool(row.get("required", False)),
            "options": row.get("options", []),
            "rows": int(row.get("rows") or 3),
            "masked": bool(row.get("masked", False)),
            "enabled": bool(row.get("enabled", True)),
            "sort": int(row.get("sort", 0)),
            "updatedAt": _fmt_time(row.get("updated_at")),
        }
        for row in rows
    ]


@router.post("/user-fields", status_code=status.HTTP_201_CREATED)
async def create_user_field(payload: UserFieldDefPayload, current_user: dict = Depends(get_current_admin_user)) -> dict[str, Any]:
    main_id = _main_id(current_user)
    db = get_db()
    now = _now()
    doc = {
        "main_id": main_id,
        "field_key": payload.fieldKey,
        "label": payload.label,
        "field_type": payload.fieldType,
        "required": payload.required,
        "options": payload.options,
        "rows": payload.rows,
        "masked": payload.masked,
        "enabled": payload.enabled,
        "sort": payload.sort,
        "created_at": now,
        "updated_at": now,
    }
    try:
        result = await db[USER_FIELD_DEF_COLLECTION].insert_one(doc)
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="字段key已存在") from exc
    await _write_audit(main_id, str(current_user.get("username", "")), "create", "user_field", str(result.inserted_id), payload.model_dump())
    return {"id": str(result.inserted_id)}


@router.put("/user-fields/{field_id}")
async def update_user_field(field_id: str, payload: UserFieldDefPayload, current_user: dict = Depends(get_current_admin_user)) -> dict[str, bool]:
    main_id = _main_id(current_user)
    db = get_db()
    field_oid = _safe_oid(field_id, "字段ID无效")
    exists = await db[USER_FIELD_DEF_COLLECTION].find_one({"_id": field_oid, "main_id": main_id})
    if exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="字段不存在")
    try:
        await db[USER_FIELD_DEF_COLLECTION].update_one(
            {"_id": field_oid, "main_id": main_id},
            {
                "$set": {
                    "field_key": payload.fieldKey,
                    "label": payload.label,
                    "field_type": payload.fieldType,
                    "required": payload.required,
                    "options": payload.options,
                    "rows": payload.rows,
                    "masked": payload.masked,
                    "enabled": payload.enabled,
                    "sort": payload.sort,
                    "updated_at": _now(),
                }
            },
        )
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="字段key已存在") from exc
    await _write_audit(main_id, str(current_user.get("username", "")), "update", "user_field", field_id, payload.model_dump())
    return {"success": True}


@router.delete("/user-fields/{field_id}")
async def delete_user_field(field_id: str, current_user: dict = Depends(get_current_admin_user)) -> dict[str, bool]:
    main_id = _main_id(current_user)
    db = get_db()
    field_oid = _safe_oid(field_id, "字段ID无效")
    field = await db[USER_FIELD_DEF_COLLECTION].find_one({"_id": field_oid, "main_id": main_id})
    if field is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="字段不存在")
    await db[USER_FIELD_DEF_COLLECTION].delete_one({"_id": field_oid, "main_id": main_id})
    await db[USER_FIELD_VALUE_COLLECTION].delete_many({"main_id": main_id, "field_key": field.get("field_key", "")})
    await _write_audit(main_id, str(current_user.get("username", "")), "delete", "user_field", field_id, {})
    return {"success": True}


@router.get("/users/{user_id}/custom-fields")
async def get_user_custom_fields(user_id: str, current_user: dict = Depends(get_current_admin_user)) -> dict[str, Any]:
    main_id = _main_id(current_user)
    db = get_db()
    user_oid = _safe_oid(user_id, "用户ID无效")
    user = await db[USER_COLLECTION].find_one({"_id": user_oid, "main_id": main_id})
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    defs = await db[USER_FIELD_DEF_COLLECTION].find({"main_id": main_id, "enabled": True}).to_list(length=500)
    values = await db[USER_FIELD_VALUE_COLLECTION].find({"main_id": main_id, "user_id": user_id}).to_list(length=500)
    value_map = {row.get("field_key", ""): row.get("value") for row in values}
    return {
        "fields": [
            {
                "fieldKey": row.get("field_key", ""),
                "label": row.get("label", ""),
                "fieldType": row.get("field_type", "text"),
                "required": bool(row.get("required", False)),
                "options": row.get("options", []),
                "rows": int(row.get("rows") or 3),
                "masked": bool(row.get("masked", False)),
                "value": value_map.get(row.get("field_key", ""), None),
            }
            for row in defs
        ]
    }


@router.put("/users/{user_id}/custom-fields")
async def upsert_user_custom_fields(
    user_id: str,
    payload: UserCustomValuesPayload,
    current_user: dict = Depends(get_current_admin_user),
) -> dict[str, bool]:
    main_id = _main_id(current_user)
    db = get_db()
    user_oid = _safe_oid(user_id, "用户ID无效")
    user = await db[USER_COLLECTION].find_one({"_id": user_oid, "main_id": main_id})
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    defs = await db[USER_FIELD_DEF_COLLECTION].find({"main_id": main_id, "enabled": True}).to_list(length=500)
    allowed_keys = {row.get("field_key", "") for row in defs}
    for key, value in payload.values.items():
        if key not in allowed_keys:
            continue
        await db[USER_FIELD_VALUE_COLLECTION].update_one(
            {"main_id": main_id, "user_id": user_id, "field_key": key},
            {"$set": {"value": value, "updated_at": _now()}, "$setOnInsert": {"created_at": _now()}},
            upsert=True,
        )
    await _write_audit(main_id, str(current_user.get("username", "")), "update", "user_custom_fields", user_id, payload.model_dump())
    return {"success": True}


@router.get("/users/{user_id}/identities")
async def list_user_identities(user_id: str, current_user: dict = Depends(get_current_admin_user)) -> list[dict[str, Any]]:
    main_id = _main_id(current_user)
    db = get_db()
    user_oid = _safe_oid(user_id, "用户ID无效")
    user = await db[USER_COLLECTION].find_one({"_id": user_oid, "main_id": main_id})
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    rows = await db[USER_IDENTITY_COLLECTION].find({"main_id": main_id, "user_id": user_id}).to_list(length=100)
    return [
        {
            "id": str(row["_id"]),
            "provider": row.get("provider", ""),
            "providerUserId": row.get("provider_user_id", ""),
            "unionId": row.get("union_id", ""),
            "corpId": row.get("corp_id", ""),
            "tenantKey": row.get("tenant_key", ""),
            "isPrimary": bool(row.get("is_primary", False)),
            "bindStatus": row.get("bind_status", "bound"),
            "lastSyncAt": _fmt_time(row.get("last_sync_at")),
        }
        for row in rows
    ]


@router.post("/users/{user_id}/identities", status_code=status.HTTP_201_CREATED)
async def add_user_identity(
    user_id: str,
    payload: UserIdentityPayload,
    current_user: dict = Depends(get_current_admin_user),
) -> dict[str, Any]:
    main_id = _main_id(current_user)
    db = get_db()
    user_oid = _safe_oid(user_id, "用户ID无效")
    user = await db[USER_COLLECTION].find_one({"_id": user_oid, "main_id": main_id})
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    now = _now()
    try:
        result = await db[USER_IDENTITY_COLLECTION].insert_one(
            {
                "main_id": main_id,
                "user_id": user_id,
                "provider": payload.provider,
                "provider_user_id": payload.providerUserId,
                "union_id": payload.unionId,
                "corp_id": payload.corpId,
                "tenant_key": payload.tenantKey,
                "is_primary": payload.isPrimary,
                "bind_status": payload.bindStatus,
                "last_sync_at": None,
                "created_at": now,
                "updated_at": now,
            }
        )
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该外部身份已被绑定") from exc
    await _write_audit(main_id, str(current_user.get("username", "")), "create", "user_identity", str(result.inserted_id), payload.model_dump())
    return {"id": str(result.inserted_id)}


@router.delete("/user-identities/{identity_id}")
async def delete_user_identity(identity_id: str, current_user: dict = Depends(get_current_admin_user)) -> dict[str, bool]:
    main_id = _main_id(current_user)
    db = get_db()
    id_oid = _safe_oid(identity_id, "身份ID无效")
    row = await db[USER_IDENTITY_COLLECTION].find_one({"_id": id_oid, "main_id": main_id})
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="身份绑定不存在")
    await db[USER_IDENTITY_COLLECTION].delete_one({"_id": id_oid, "main_id": main_id})
    await _write_audit(main_id, str(current_user.get("username", "")), "delete", "user_identity", identity_id, {})
    return {"success": True}


@router.get("/audit-logs")
async def list_audit_logs(
    current_user: dict = Depends(get_current_admin_user),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=200),
) -> dict[str, Any]:
    main_id = _main_id(current_user)
    db = get_db()
    skip = (page - 1) * pageSize
    total = await db[AUDIT_LOG_COLLECTION].count_documents({"main_id": main_id})
    rows = (
        await db[AUDIT_LOG_COLLECTION]
        .find({"main_id": main_id})
        .sort("created_at", -1)
        .skip(skip)
        .limit(pageSize)
        .to_list(length=pageSize)
    )
    return {
        "page": page,
        "pageSize": pageSize,
        "total": total,
        "items": [
            {
                "id": str(row["_id"]),
                "operator": row.get("operator", ""),
                "action": row.get("action", ""),
                "targetType": row.get("target_type", ""),
                "targetId": row.get("target_id", ""),
                "payload": row.get("payload", {}),
                "createdAt": _fmt_time(row.get("created_at")),
            }
            for row in rows
        ],
    }
