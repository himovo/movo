from __future__ import annotations

import base64
from datetime import datetime, timedelta
import hashlib
import hmac
import json
import logging
import secrets
import time
import uuid
from typing import Any, Optional

from bson import ObjectId
from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.db import get_db
from app.core.end_user_auth import build_session_token, parse_and_verify_session_token, verify_password
from app.core.tenant import DEFAULT_MAIN_ID, add_main_scope, resolve_main_id
from app.utils.oss_uploader import ObjectStorageClient
from app.utils.uploads import read_upload_with_limit
from app.governance.position_policy import MongoEmployeePolicyResolver
from app.services.end_user_tenant_access import load_tenant_candidates, resolve_space_type
from app.services.end_user_session import resolve_session_user as _resolve_session_user

router = APIRouter()
logger = logging.getLogger(__name__)

USER_COLLECTION = "end_users"
USER_SESSION_COLLECTION = "end_user_sessions"
LOGIN_CHALLENGE_COLLECTION = "end_user_login_challenges"
ADMIN_ACCOUNT_COLLECTION = "admin_accounts"
ADMIN_SESSION_COLLECTION = "admin_sessions"
USER_INVITE_COLLECTION = "user_invites"
USER_ORG_REL_COLLECTION = "end_user_org_relations"
DEPARTMENT_COLLECTION = "org_units"
class ApiResponse(BaseModel):
    code: int = 0
    message: Optional[str] = None
    data: Optional[object] = None


def _t(request: Request, zh: str, en: str) -> str:
    lang = request.headers.get("accept-language", "")
    if "en" in lang.lower():
        return en
    return zh


async def _check_org_name_duplicate(org_name: str) -> bool:
    name = org_name.strip()
    if not name or name == "个人空间":
        return False
    db = get_db()
    existing = await db["organizations"].find_one({"org_name": name})
    return existing is not None


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)
    mainId: str = Field(default="", max_length=64)


class SelectTenantRequest(BaseModel):
    challengeToken: str = Field(min_length=8, max_length=256)
    mainId: str = Field(min_length=1, max_length=64)


class SwitchTenantRequest(BaseModel):
    mainId: str = Field(min_length=1, max_length=64)


class ProfileUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)


def _now() -> datetime:
    return datetime.utcnow()


def _extract_token(authorization: str | None) -> str:
    raw = str(authorization or "").strip()
    if not raw.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing_bearer_token")
    token = raw[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing_bearer_token")
    return token


def _space_type_from_user(user: dict[str, Any]) -> str:
    return resolve_space_type(user)


def _is_valid_tenant_main_id(main_id: str) -> bool:
    value = str(main_id or "").strip()
    return bool(value) and value != DEFAULT_MAIN_ID


def _profile_from_user(
    user: dict[str, Any],
    main_id: str,
    tenant: dict[str, Any],
    available_tenants: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    avatar = str(user.get("avatar") or "").strip()
    avatar_object_path = str(user.get("avatar_object_path") or "").strip()
    if avatar_object_path:
        try:
            avatar = ObjectStorageClient().sign_url(avatar_object_path)
        except Exception:
            pass
    return {
        "userId": str(user.get("_id") or ""),
        "name": str(user.get("name") or ""),
        "username": str(user.get("login_name") or ""),
        "phone": str(user.get("mobile") or ""),
        "email": str(user.get("email") or ""),
        "avatar": avatar,
        "mainId": resolve_main_id(main_id),
        "orgName": str(tenant.get("orgName") or user.get("org_name") or resolve_main_id(main_id)),
        "spaceType": str(tenant.get("spaceType") or _space_type_from_user(user)),
        "canAccessAdmin": bool(tenant.get("canAccessAdmin")),
        "edition": str(tenant.get("edition") or "cloud"),
        "billingEnabled": bool(tenant.get("billingEnabled", True)),
        "memberLimit": tenant.get("memberLimit"),
        "availableTenants": list(available_tenants or []),
    }


async def _profile_with_policy(user: dict[str, Any], main_id: str, available_tenants: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    tenant = (await load_tenant_candidates(get_db(), [user]))[0]
    normalized_tenants = [
        tenant if resolve_main_id(item.get("mainId")) == resolve_main_id(main_id) else {**item, "canAccessAdmin": bool(item.get("canAccessAdmin"))}
        for item in list(available_tenants or [])
    ]
    if not any(resolve_main_id(item.get("mainId")) == resolve_main_id(main_id) for item in normalized_tenants):
        normalized_tenants.append(tenant)
    profile = _profile_from_user(user, main_id, tenant, normalized_tenants)
    policy = await MongoEmployeePolicyResolver().resolve(resolve_main_id(main_id), str(user.get("_id") or ""))
    profile["agentPolicy"] = policy.public_snapshot()
    return profile


def _avatar_fields_from_user(user: dict[str, Any] | None) -> dict[str, str]:
    if not user:
        return {}
    avatar = str(user.get("avatar") or "").strip()
    avatar_object_path = str(user.get("avatar_object_path") or "").strip()
    fields: dict[str, str] = {}
    if avatar:
        fields["avatar"] = avatar
    if avatar_object_path:
        fields["avatar_object_path"] = avatar_object_path
    return fields


async def _backfill_missing_avatar(
    target_user: dict[str, Any],
    available_tenants: list[dict[str, Any]],
    preferred_source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if _avatar_fields_from_user(target_user):
        return target_user

    source_fields = _avatar_fields_from_user(preferred_source)
    db = get_db()
    if not source_fields:
        target_user_id = str(target_user.get("_id") or "")
        for candidate in available_tenants:
            candidate_user_id = str(candidate.get("userId") or "")
            if candidate_user_id == target_user_id or not ObjectId.is_valid(candidate_user_id):
                continue
            candidate_user = await db[USER_COLLECTION].find_one(
                {"_id": ObjectId(candidate_user_id), "status": "active"}
            )
            source_fields = _avatar_fields_from_user(candidate_user)
            if source_fields:
                break

    if not source_fields:
        return target_user

    missing_avatar_filter = {
        "_id": target_user["_id"],
        "$and": [
            {"$or": [{"avatar": {"$exists": False}}, {"avatar": ""}, {"avatar": None}]},
            {
                "$or": [
                    {"avatar_object_path": {"$exists": False}},
                    {"avatar_object_path": ""},
                    {"avatar_object_path": None},
                ]
            },
        ],
    }
    result = await db[USER_COLLECTION].update_one(
        missing_avatar_filter,
        {"$set": {**source_fields, "updated_at": _now()}},
    )
    if result.modified_count:
        target_user.update(source_fields)
    return target_user


async def _find_verified_users(username: str, password: str, preferred_main_id: str | None) -> list[dict[str, Any]]:
    db = get_db()
    identity = str(username or "").strip()
    query: dict[str, Any] = {
        "status": "active",
        "$or": [
            {"login_name": identity},
            {"email": identity.lower()},
        ],
    }
    if preferred_main_id:
        query = add_main_scope(query, preferred_main_id)
    rows = await db[USER_COLLECTION].find(query).to_list(length=200)
    matched: list[dict[str, Any]] = []
    for row in rows:
        password_hash = str(row.get("password_hash") or "")
        password_salt = str(row.get("password_salt") or "")
        if not password_hash or not password_salt:
            continue
        if verify_password(password, password_hash, password_salt):
            matched.append(row)
    return matched


async def _create_session(user_doc: dict[str, Any], available_tenants: list[dict[str, Any]]) -> dict[str, Any]:
    db = get_db()
    settings = get_settings()
    ttl_seconds = max(300, int(settings.END_USER_AUTH_TOKEN_TTL_SECONDS))
    now = _now()
    token_id = secrets.token_urlsafe(24)
    token = build_session_token(settings.END_USER_AUTH_SECRET, token_id)
    expires_at = now + timedelta(seconds=ttl_seconds)
    main_id = resolve_main_id(user_doc.get("main_id"))
    await db[USER_SESSION_COLLECTION].insert_one(
        {
            "token_id": token_id,
            "user_id": str(user_doc["_id"]),
            "username": str(user_doc.get("login_name") or ""),
            "main_id": main_id,
            "available_tenants": available_tenants,
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "last_seen_at": now,
            "expires_at": expires_at,
        }
    )
    await db[USER_COLLECTION].update_one(
        {"_id": user_doc["_id"]},
        {"$set": {"last_login_at": now, "updated_at": now}},
    )
    return {
        "token": token,
        "profile": await _profile_with_policy(user_doc, main_id, available_tenants),
        "expiresAt": expires_at.isoformat(),
    }


async def _create_login_challenge(username: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    db = get_db()
    now = _now()
    challenge_token = secrets.token_urlsafe(28)
    expires_at = now + timedelta(minutes=5)
    await db[LOGIN_CHALLENGE_COLLECTION].insert_one(
        {
            "challenge_token": challenge_token,
            "username": username,
            "candidates": candidates,
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "expires_at": expires_at,
        }
    )
    return {"challengeToken": challenge_token, "candidates": candidates, "expiresAt": expires_at.isoformat()}


@router.post("/auth/login", response_model=ApiResponse)
async def login(payload: LoginRequest) -> ApiResponse:
    db = get_db()
    setup_state = await db["system_bootstrap"].find_one({"_id": "singleton"}, {"completed": 1})
    if not setup_state or not bool(setup_state.get("completed")):
        return ApiResponse(code=1, message="系统尚未完成初始化，请先在管理后台执行 Setup")

    username = payload.username.strip()
    preferred_main_id = resolve_main_id(payload.mainId) if str(payload.mainId or "").strip() else None
    matched_users = await _find_verified_users(username=username, password=payload.password, preferred_main_id=preferred_main_id)
    if not matched_users and preferred_main_id:
        matched_users = await _find_verified_users(username=username, password=payload.password, preferred_main_id=None)
    if not matched_users:
        return ApiResponse(code=1, message="用户名或密码错误")

    # End-user runtime does not accept fallback tenant id "default".
    matched_users = [item for item in matched_users if _is_valid_tenant_main_id(resolve_main_id(item.get("main_id")))]
    if not matched_users:
        return ApiResponse(code=1, message="当前账号未绑定有效组织，请联系管理员配置租户ID")

    candidates = await load_tenant_candidates(db, matched_users)
    if len(candidates) > 1 and not preferred_main_id:
        challenge = await _create_login_challenge(username=username, candidates=candidates)
        return ApiResponse(
            code=1001,
            message="请选择要进入的组织",
            data={
                "requiresTenantSelection": True,
                "challengeToken": challenge["challengeToken"],
                "candidates": challenge["candidates"],
                "expiresAt": challenge["expiresAt"],
            },
        )

    main_id = preferred_main_id or candidates[0]["mainId"]
    if not _is_valid_tenant_main_id(main_id):
        return ApiResponse(code=1, message="组织ID无效，请联系管理员配置租户ID")
    target = next((item for item in matched_users if resolve_main_id(item.get("main_id")) == main_id), matched_users[0])
    session_payload = await _create_session(target, candidates)
    return ApiResponse(code=0, data=session_payload)


@router.post("/auth/login/select-tenant", response_model=ApiResponse)
async def select_tenant_login(payload: SelectTenantRequest) -> ApiResponse:
    db = get_db()
    now = _now()
    challenge = await db[LOGIN_CHALLENGE_COLLECTION].find_one(
        {"challenge_token": payload.challengeToken, "status": "active"}
    )
    if not challenge:
        return ApiResponse(code=1, message="登录挑战不存在或已失效")
    if challenge.get("expires_at") and challenge["expires_at"] < now:
        await db[LOGIN_CHALLENGE_COLLECTION].update_one(
            {"_id": challenge["_id"]},
            {"$set": {"status": "expired", "updated_at": now}},
        )
        return ApiResponse(code=1, message="登录挑战已过期")

    candidates = list(challenge.get("candidates") or [])
    selected_main_id = resolve_main_id(payload.mainId)
    if not _is_valid_tenant_main_id(selected_main_id):
        return ApiResponse(code=1, message="组织ID无效")
    selected = next((item for item in candidates if resolve_main_id(item.get("mainId")) == selected_main_id), None)
    if not selected:
        return ApiResponse(code=1, message="所选组织不可用")

    user_id = str(selected.get("userId") or "")
    if not ObjectId.is_valid(user_id):
        return ApiResponse(code=1, message="用户数据异常")
    main_id = resolve_main_id(selected.get("mainId"))
    if not _is_valid_tenant_main_id(main_id):
        return ApiResponse(code=1, message="组织ID无效")
    user_doc = await db[USER_COLLECTION].find_one(add_main_scope({"_id": ObjectId(user_id), "status": "active"}, main_id))
    if not user_doc:
        return ApiResponse(code=1, message="用户不存在或已禁用")

    await db[LOGIN_CHALLENGE_COLLECTION].update_one(
        {"_id": challenge["_id"]},
        {"$set": {"status": "used", "updated_at": now}},
    )
    session_payload = await _create_session(user_doc, candidates)
    return ApiResponse(code=0, data=session_payload)


@router.post("/auth/switch-tenant", response_model=ApiResponse)
async def switch_tenant(
    payload: SwitchTenantRequest,
    authorization: str | None = Header(default=None),
) -> ApiResponse:
    resolved = await _resolve_session_user(authorization)
    session_doc = resolved["session"]
    db = get_db()
    available_tenants = list(session_doc.get("available_tenants") or [])
    target_main_id = resolve_main_id(payload.mainId)
    if not _is_valid_tenant_main_id(target_main_id):
        return ApiResponse(code=1, message="组织ID无效")
    target = next((item for item in available_tenants if resolve_main_id(item.get("mainId")) == target_main_id), None)
    if not target:
        return ApiResponse(code=1, message="当前账号不可切换到该组织")
    user_id = str(target.get("userId") or "")
    if not ObjectId.is_valid(user_id):
        return ApiResponse(code=1, message="用户数据异常")
    user_doc = await db[USER_COLLECTION].find_one(add_main_scope({"_id": ObjectId(user_id), "status": "active"}, target_main_id))
    if not user_doc:
        return ApiResponse(code=1, message="组织内用户不存在或已禁用")
    user_doc = await _backfill_missing_avatar(
        user_doc,
        available_tenants,
        preferred_source=resolved["user"],
    )
    session_payload = await _create_session(user_doc, available_tenants)
    await db[USER_SESSION_COLLECTION].update_one(
        {"_id": session_doc["_id"]},
        {"$set": {"status": "switched", "updated_at": _now()}},
    )
    return ApiResponse(code=0, data=session_payload)


@router.get("/auth/me", response_model=ApiResponse)
async def me(authorization: str | None = Header(default=None)) -> ApiResponse:
    resolved = await _resolve_session_user(authorization)
    stale_tenants = list(resolved["session"].get("available_tenants") or [])
    user = await _backfill_missing_avatar(resolved["user"], stale_tenants)
    available_tenants = await _load_available_tenants(str(user.get("login_name") or ""))
    await get_db()[USER_SESSION_COLLECTION].update_one(
        {"_id": resolved["session"]["_id"]},
        {"$set": {"available_tenants": available_tenants, "updated_at": _now()}},
    )
    return ApiResponse(code=0, data=await _profile_with_policy(user, resolved["main_id"], available_tenants))


@router.patch("/auth/profile", response_model=ApiResponse)
async def update_profile(
    payload: ProfileUpdateRequest,
    authorization: str | None = Header(default=None),
) -> ApiResponse:
    resolved = await _resolve_session_user(authorization)
    current_user = resolved["user"]
    name = payload.name.strip()
    if not name:
        return ApiResponse(code=1, message="用户名称不能为空")
    db = get_db()
    now = _now()
    mobile = str(current_user.get("mobile") or "").strip()
    login_name = str(current_user.get("login_name") or "").strip()
    user_query: dict[str, Any] = {"mobile": mobile} if mobile else {"login_name": login_name}
    admin_query: dict[str, Any] = {"phone": mobile} if mobile else {"username": login_name}
    await db[USER_COLLECTION].update_many(
        {**user_query, "status": "active"},
        {"$set": {"name": name, "updated_at": now}},
    )
    await db[ADMIN_ACCOUNT_COLLECTION].update_many(
        {**admin_query, "status": "active"},
        {"$set": {"display_name": name, "updated_at": now}},
    )
    refreshed = await db[USER_COLLECTION].find_one({"_id": current_user["_id"]})
    available_tenants = await _load_available_tenants(login_name)
    return ApiResponse(
        code=0,
        message="个人资料已更新",
        data=await _profile_with_policy(refreshed or current_user, resolved["main_id"], available_tenants),
    )


@router.post("/auth/profile/avatar", response_model=ApiResponse)
async def upload_profile_avatar(
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
) -> ApiResponse:
    resolved = await _resolve_session_user(authorization)
    current_user = resolved["user"]
    content_type = str(file.content_type or "").lower()
    allowed_types = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }
    suffix = allowed_types.get(content_type)
    if not suffix:
        return ApiResponse(code=1, message="头像仅支持 JPG、PNG 或 WebP 图片")
    content = await read_upload_with_limit(file, max_bytes=3 * 1024 * 1024, label="Avatar")
    if not content:
        return ApiResponse(code=1, message="头像文件不能为空")
    valid_signature = (
        (content_type == "image/jpeg" and content.startswith(b"\xff\xd8\xff"))
        or (content_type == "image/png" and content.startswith(b"\x89PNG\r\n\x1a\n"))
        or (
            content_type == "image/webp"
            and len(content) >= 12
            and content[:4] == b"RIFF"
            and content[8:12] == b"WEBP"
        )
    )
    if not valid_signature:
        return ApiResponse(code=1, message="头像文件格式无效")

    uploader = ObjectStorageClient()
    user_id = str(current_user["_id"])
    avatar_url, object_path = uploader.upload_bytes_with_path(
        content,
        user_id=f"avatars/{user_id}",
        file_name=f"avatar_{uuid.uuid4().hex}{suffix}",
        content_type=content_type,
    )
    db = get_db()
    now = _now()
    login_name = str(current_user.get("login_name") or "").strip()
    available_tenants = list(resolved["session"].get("available_tenants") or [])
    tenant_user_ids = {
        ObjectId(str(item.get("userId")))
        for item in available_tenants
        if ObjectId.is_valid(str(item.get("userId") or ""))
    }
    tenant_user_ids.add(current_user["_id"])
    await db[USER_COLLECTION].update_many(
        {"_id": {"$in": list(tenant_user_ids)}, "status": "active"},
        {"$set": {"avatar": avatar_url, "avatar_object_path": object_path, "updated_at": now}},
    )
    refreshed = await db[USER_COLLECTION].find_one({"_id": current_user["_id"]})
    if not available_tenants:
        available_tenants = await _load_available_tenants(login_name)
    return ApiResponse(
        code=0,
        message="头像已更新",
        data=await _profile_with_policy(refreshed or current_user, resolved["main_id"], available_tenants),
    )


@router.post("/auth/logout", response_model=ApiResponse)
async def logout(authorization: str | None = Header(default=None)) -> ApiResponse:
    db = get_db()
    settings = get_settings()
    token = _extract_token(authorization)
    token_id = parse_and_verify_session_token(settings.END_USER_AUTH_SECRET, token)
    if token_id:
        await db[USER_SESSION_COLLECTION].update_one(
            {"token_id": token_id},
            {"$set": {"status": "revoked", "updated_at": _now()}},
        )
    return ApiResponse(code=0, data={"success": True})


def _create_admin_token(subject: dict, secret: str, expires_in_seconds: int = 12 * 60 * 60) -> tuple[str, int, str]:
    expires_at = int(time.time()) + expires_in_seconds
    session_id = str(uuid.uuid4())
    payload = {
        "sub": {
            **subject,
            "session_id": session_id,
        },
        "exp": expires_at,
    }
    encoded_payload = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).decode("utf-8").rstrip("=")
    
    signature = hmac.new(
        secret.encode("utf-8"),
        encoded_payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")
    return f"{encoded_payload}.{encoded_signature}", expires_at, session_id


async def _load_available_tenants(username: str) -> list[dict[str, Any]]:
    db = get_db()
    rows = await db[USER_COLLECTION].find({"login_name": username, "status": "active"}).to_list(length=200)
    candidates = await load_tenant_candidates(db, rows)
    return [item for item in candidates if _is_valid_tenant_main_id(resolve_main_id(item.get("mainId")))]


async def _ensure_root_department(main_id: str) -> str:
    db = get_db()
    now = _now()
    await db[DEPARTMENT_COLLECTION].update_one(
        {"main_id": main_id, "code": "root"},
        {
            "$setOnInsert": {
                "main_id": main_id,
                "name": "企业总部",
                "code": "root",
                "parent_id": None,
                "path_ids": [],
                "path_names": [],
                "status": "active",
                "source": "local",
                "source_dept_id": "",
                "created_at": now,
            },
            "$set": {"updated_at": now},
        },
        upsert=True,
    )
    root = await db[DEPARTMENT_COLLECTION].find_one({"main_id": main_id, "code": "root"})
    if not root:
        raise RuntimeError("组织根部门初始化失败")
    return str(root["_id"])


async def _resolve_primary_department(main_id: str, requested_department_id: str | None = None) -> str:
    db = get_db()
    if requested_department_id and ObjectId.is_valid(str(requested_department_id)):
        department = await db[DEPARTMENT_COLLECTION].find_one(
            {
                "_id": ObjectId(str(requested_department_id)),
                "main_id": main_id,
                "status": "active",
            }
        )
        if department:
            return str(department["_id"])
    return await _ensure_root_department(main_id)


async def _assign_user_primary_department(main_id: str, user_id: str, department_id: str) -> None:
    db = get_db()
    now = _now()
    await db[USER_COLLECTION].update_one(
        {"_id": ObjectId(user_id), "main_id": main_id},
        {"$set": {"primary_org_id": department_id, "updated_at": now}},
    )
    await db[USER_ORG_REL_COLLECTION].delete_many({"main_id": main_id, "user_id": user_id})
    await db[USER_ORG_REL_COLLECTION].insert_one(
        {
            "main_id": main_id,
            "user_id": user_id,
            "org_id": department_id,
            "is_primary": True,
            "created_at": now,
            "updated_at": now,
        }
    )


@router.get("/organizations/me", response_model=ApiResponse)
async def get_org_details(
    authorization: str | None = Header(default=None)
) -> ApiResponse:
    resolved = await _resolve_session_user(authorization)
    main_id = resolved["main_id"]
    current_user = resolved["user"]
    
    db = get_db()
    from app.core.billing import get_or_create_organization
    org = await get_or_create_organization(main_id, default_org_name=current_user.get("org_name") or "个人空间", owner_id=str(current_user["_id"]))
    
    current_members = await db[USER_COLLECTION].count_documents({"main_id": main_id})
    from app.core.product_edition import organization_capability_payload

    capabilities = organization_capability_payload(org)
    total_points = int(org.get("total_points") or 0)
    used_points = int(org.get("used_points") or 0)
    
    data = {
        "mainId": org.get("main_id"),
        "orgName": org.get("org_name"),
        "edition": capabilities["edition"],
        "tier": org.get("tier", "community"),
        "billingEnabled": capabilities["billingEnabled"],
        "userLimit": capabilities["memberLimit"],
        "currentMembersCount": current_members,
        "totalPoints": total_points,
        "usedPoints": used_points,
        "remainingPoints": max(0, total_points - used_points),
        "isOwnModel": bool(org.get("is_own_model", False)),
        "isOwner": str(org.get("owner_user_id")) == str(current_user["_id"]),
    }
    return ApiResponse(code=0, data=data)


@router.post("/auth/admin-sso", response_model=ApiResponse)
async def admin_sso(
    authorization: str | None = Header(default=None)
) -> ApiResponse:
    """
    单点登录（SSO）：为已登录的用户加密生成用于管理后台的 access token，
    并在 admin_sessions 中插入以允许后台免密登录。
    """
    resolved = await _resolve_session_user(authorization)
    current_user = resolved["user"]
    main_id = resolved["main_id"]
    username = current_user["login_name"]
    db = get_db()
    tenant = (await load_tenant_candidates(db, [current_user]))[0]
    if tenant.get("spaceType") != "enterprise":
        return ApiResponse(code=1, message="个人空间没有管理后台")
    if not tenant.get("canAccessAdmin"):
        return ApiResponse(code=1, message="您没有访问管理后台的权限")

    # 1. 后台账号与用户端账号分离：SSO 只校验已有后台账号，不自动补建。
    admin_account = await db[ADMIN_ACCOUNT_COLLECTION].find_one({"username": username, "main_id": main_id})
    if not admin_account or admin_account.get("status") != "active" or admin_account.get("group_code") == "member":
        return ApiResponse(code=1, message="您没有访问管理后台的权限")

    # 2. 生成 JWT token
    # 签名密钥：如果环境变量有配置则读，否则用默认开发值
    jwt_secret = get_settings().ASKAI_ADMIN_JWT_SECRET
    
    subject = {
        "username": username,
        "role_name": admin_account.get("role_name") or "平台超级管理员",
        "org_name": admin_account.get("org_name") or "个人空间",
        "main_id": main_id,
    }
    
    token, expires_at, session_id = _create_admin_token(subject, jwt_secret)
    
    # 3. 在后台活跃 session 表 (admin_sessions) 写入授权，允许直接握手通过
    admin_session = {
        "session_id": session_id,
        "username": username,
        "token_expires_at": expires_at,
        "user_agent": "AskAgentic SSO Portal",
        "ip": "127.0.0.1",
        "status": "active",
        "created_at": _now()
    }
    await db[ADMIN_SESSION_COLLECTION].insert_one(admin_session)
    
    return ApiResponse(
        code=0,
        message="单点登录凭证授权成功",
        data={
            "sso_token": token,
            "expiresAt": expires_at
        }
    )
