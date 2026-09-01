import secrets
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field

from app.api.deps import get_current_admin_user
from app.api.time_utils import utc_iso
from app.core.config import settings
from app.core.db import get_db
from app.core.security import create_access_token, decode_access_token, verify_password
from app.repositories.org_user_repository import (
    find_account_by_username,
    find_account_by_username_any_main,
    list_accounts_by_username,
    set_account_password,
    touch_account_last_login,
    update_account_avatar,
    update_account_profile,
)
from app.repositories.admin_session_repository import create_session, revoke_session
from app.repositories.setup_repository import get_setup_state


class LoginRequest(BaseModel):
    username: str
    password: str
    mainId: str = Field(default="", max_length=64)


class SelectTenantRequest(BaseModel):
    challengeToken: str = Field(min_length=12, max_length=160)
    mainId: str = Field(min_length=1, max_length=64)


class ProfileUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    email: str = Field(default="", max_length=128)
    phone: str = Field(default="", max_length=32)


class PasswordChangeRequest(BaseModel):
    currentPassword: str = Field(min_length=1, max_length=128)
    newPassword: str = Field(min_length=10, max_length=128)


router = APIRouter()
LOGIN_CHALLENGE_COLLECTION = "admin_login_challenges"
AVATAR_CONTENT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _digits_only(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _is_mobile_like(value: Any) -> bool:
    return bool(re.fullmatch(r"1[3-9]\d{9}", _digits_only(value)))


def _safe_display_name(user: dict[str, Any]) -> str:
    display_name = str(user.get("display_name") or "").strip()
    if not display_name:
        return ""
    display_digits = _digits_only(display_name)
    if _is_mobile_like(display_name) and display_digits in {
        _digits_only(user.get("username")),
        _digits_only(user.get("phone")),
    }:
        return ""
    return display_name


def _safe_path_part(value: Any, fallback: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(value or "").strip()).strip(".-")
    return normalized[:80] or fallback


def _avatar_extension(content_type: str, filename: str) -> str:
    suffix = Path(filename or "").suffix.lower().lstrip(".")
    ext = AVATAR_CONTENT_TYPES.get(content_type.lower())
    if ext and suffix in {"", "jpg", "jpeg", "png", "webp"}:
        return ext
    if suffix == "jpeg":
        suffix = "jpg"
    if suffix in {"jpg", "png", "webp"} and content_type.lower() in AVATAR_CONTENT_TYPES:
        return suffix
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="头像仅支持 JPG、PNG、WebP")


def _validate_avatar_signature(data: bytes, ext: str) -> None:
    if ext == "jpg" and data.startswith(b"\xff\xd8\xff"):
        return
    if ext == "png" and data.startswith(b"\x89PNG\r\n\x1a\n"):
        return
    if ext == "webp" and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="头像文件内容无效")


def _avatar_public_url(relative_path: str) -> str:
    return f"/static/{relative_path.strip('/')}"


def _profile_from_user(user: dict[str, Any], main_id: str) -> dict[str, object]:
    return {
        "name": _safe_display_name(user),
        "roleName": user.get("role_name") or "组织管理员",
        "orgName": user.get("org_name") or user.get("group_code") or "组织账户",
        "username": user.get("username") or "",
        "email": user.get("email") or "",
        "phone": user.get("phone") or "",
        "avatarUrl": user.get("avatar_url") or "",
        "avatarUpdatedAt": utc_iso(user.get("avatar_updated_at")),
        "lastLoginAt": utc_iso(user.get("last_login_at")),
        "mainId": main_id,
    }


def _candidate_from_user(user: dict[str, Any]) -> dict[str, object]:
    main_id = str(user.get("main_id") or "")
    return {
        "mainId": main_id,
        "orgName": user.get("org_name") or user.get("group_code") or "组织账户",
        "roleName": user.get("role_name") or "组织管理员",
        "displayName": user.get("display_name") or user.get("username") or "",
        "username": user.get("username") or "",
    }


async def _create_login_challenge(username: str, candidates: list[dict[str, object]]) -> dict[str, object]:
    db = get_db()
    now = _now()
    token = secrets.token_urlsafe(32)
    expires_at = now + timedelta(minutes=5)
    await db[LOGIN_CHALLENGE_COLLECTION].insert_one(
        {
            "challenge_token": token,
            "username": username,
            "candidates": candidates,
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "expires_at": expires_at,
        }
    )
    return {
        "requiresTenantSelection": True,
        "challengeToken": token,
        "candidates": candidates,
        "expiresAt": expires_at.isoformat(),
    }


async def _issue_login_response(user: dict[str, Any], main_id: str, request: Request) -> dict[str, object]:
    await touch_account_last_login(user["username"], main_id)
    profile = _profile_from_user(user, main_id)
    token, expires_at, session_id = create_access_token(
        {
            "username": user["username"],
            "role_name": profile["roleName"],
            "org_name": profile["orgName"],
            "main_id": main_id,
        }
    )
    await create_session(
        session_id=session_id,
        username=user["username"],
        token_expires_at=expires_at,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    return {
        "token": token,
        "profile": profile,
    }


def _password_matches(user: dict[str, Any], password: str) -> bool:
    password_hash = user.get("password_hash") or ""
    password_salt = user.get("password_salt") or ""
    return bool(password_hash and password_salt and verify_password(password, password_hash, password_salt))


@router.post("/login")
async def login(payload: LoginRequest, request: Request) -> dict[str, object]:
    requested_main_id = payload.mainId.strip()
    username = payload.username.strip()

    if requested_main_id:
        main_id = requested_main_id
        user = await find_account_by_username(username, main_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
        if user.get("status") != "active":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin user is disabled")
        if not _password_matches(user, payload.password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
        return await _issue_login_response(user, main_id, request)

    accounts = await list_accounts_by_username(username)
    matched_users = [
        account
        for account in accounts
        if account.get("status") == "active" and _password_matches(account, payload.password)
    ]

    if not matched_users:
        setup_state = await get_setup_state()
        main_id = str((setup_state or {}).get("main_id") or "").strip() or settings.bootstrap_main_id
        user = await find_account_by_username(username, main_id)
        if user is None:
            # Compatibility fallback:
            # if tenant is not explicitly provided by client, try globally unique username.
            user = await find_account_by_username_any_main(username)
            if user is not None:
                main_id = str(user.get("main_id") or main_id)
        if user is not None and user.get("status") == "active" and _password_matches(user, payload.password):
            matched_users = [user]

    if len(matched_users) > 1:
        candidates = [_candidate_from_user(user) for user in matched_users]
        return await _create_login_challenge(username, candidates)

    user = matched_users[0] if matched_users else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    if user.get("status") != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin user is disabled")
    main_id = str(user.get("main_id") or settings.bootstrap_main_id)
    return await _issue_login_response(user, main_id, request)


@router.post("/login/select-tenant")
async def select_tenant(payload: SelectTenantRequest, request: Request) -> dict[str, object]:
    db = get_db()
    now = _now()
    challenge = await db[LOGIN_CHALLENGE_COLLECTION].find_one(
        {"challenge_token": payload.challengeToken, "status": "active"}
    )
    if not challenge:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Login challenge not found")
    expires_at = _as_utc(challenge.get("expires_at"))
    if expires_at and expires_at < now:
        await db[LOGIN_CHALLENGE_COLLECTION].update_one(
            {"_id": challenge["_id"]},
            {"$set": {"status": "expired", "updated_at": now}},
        )
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Login challenge expired")

    candidates = list(challenge.get("candidates") or [])
    selected = next((item for item in candidates if str(item.get("mainId") or "") == payload.mainId), None)
    if not selected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Selected organization is not available")

    user = await find_account_by_username(str(challenge.get("username") or ""), payload.mainId)
    if user is None or user.get("status") != "active":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin user is unavailable")

    await db[LOGIN_CHALLENGE_COLLECTION].update_one(
        {"_id": challenge["_id"]},
        {"$set": {"status": "used", "updated_at": now, "used_main_id": payload.mainId}},
    )
    return await _issue_login_response(user, payload.mainId, request)


@router.get("/me")
async def me(current_user: dict = Depends(get_current_admin_user)) -> dict[str, object]:
    return _profile_from_user(current_user, str(current_user.get("main_id", settings.bootstrap_main_id)))


@router.patch("/me")
async def update_me(
    payload: ProfileUpdateRequest,
    current_user: dict = Depends(get_current_admin_user),
) -> dict[str, object]:
    main_id = str(current_user.get("main_id", settings.bootstrap_main_id))
    display_name = payload.name.strip()
    if not display_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="姓名不能为空")
    updated = await update_account_profile(
        str(current_user["username"]),
        main_id,
        {
            "display_name": display_name,
            "email": payload.email.strip(),
            "phone": payload.phone.strip(),
        },
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin user is unavailable")
    return _profile_from_user(updated, main_id)


@router.post("/me/password")
async def change_my_password(
    payload: PasswordChangeRequest,
    authorization: str | None = Header(default=None),
    current_user: dict = Depends(get_current_admin_user),
) -> dict[str, bool]:
    if not _password_matches(current_user, payload.currentPassword):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前密码不正确")
    if payload.currentPassword == payload.newPassword:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="新密码不能与当前密码相同")

    main_id = str(current_user.get("main_id", settings.bootstrap_main_id))
    await set_account_password(str(current_user["username"]), payload.newPassword, main_id)

    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "", 1).strip()
        decoded = decode_access_token(token)
        subject = decoded.get("sub") or {}
        session_id = subject.get("session_id")
        if session_id:
            await revoke_session(str(session_id))
    return {"success": True}


@router.post("/me/avatar")
async def upload_my_avatar(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_admin_user),
) -> dict[str, object]:
    content_type = str(file.content_type or "").lower()
    ext = _avatar_extension(content_type, file.filename or "")
    max_bytes = int(settings.avatar_max_upload_mb or 2) * 1024 * 1024
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = await file.read(256 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > max_bytes:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="头像文件不能超过 2MB")
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="头像文件不能为空")
    _validate_avatar_signature(data, ext)

    main_id = str(current_user.get("main_id", settings.bootstrap_main_id))
    username = str(current_user["username"])
    relative_dir = f"admin-avatars/{_safe_path_part(main_id, 'default')}"
    filename = f"{_safe_path_part(username, 'user')}-{uuid.uuid4().hex}.{ext}"
    relative_path = f"{relative_dir}/{filename}"
    static_root = Path(settings.admin_static_dir).expanduser().resolve()
    target = (static_root / relative_path).resolve()
    if static_root not in target.parents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="头像路径无效")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)

    avatar_url = _avatar_public_url(relative_path)
    updated = await update_account_avatar(username, main_id, avatar_url)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin user is unavailable")
    return _profile_from_user(updated, main_id)


@router.post("/logout")
async def logout(
    authorization: str | None = Header(default=None),
    current_user: dict = Depends(get_current_admin_user),
) -> dict[str, bool]:
    del current_user
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "", 1).strip()
        payload = decode_access_token(token)
        subject = payload.get("sub") or {}
        session_id = subject.get("session_id")
        if session_id:
            await revoke_session(str(session_id))
    return {"success": True}
