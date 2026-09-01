from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timedelta
import hashlib
import hmac
import json
import logging
import re
import secrets
import smtplib
import time
import uuid
from typing import Any, Optional
from email.message import EmailMessage
from email.utils import formataddr
from urllib.parse import quote

from bson import ObjectId
from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile
import httpx
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

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
REGISTRATION_ATTEMPT_COLLECTION = "end_user_registration_attempts"
EMAIL_VERIFICATION_COLLECTION = "end_user_email_verifications"
SMS_VERIFICATION_COLLECTION = "end_user_sms_verifications"
_registration_attempt_indexes_ready = False
_email_verification_indexes_ready = False
_sms_verification_indexes_ready = False

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CN_MOBILE_RE = re.compile(r"^1[3-9]\d{9}$")


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


class EmailVerificationRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    purpose: str = Field(default="register", pattern=r"^(register|password_reset)$")


class PasswordResetConfirmRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    code: str = Field(..., min_length=4, max_length=12)
    newPassword: str = Field(..., min_length=6, max_length=128)


class SmsVerificationRequest(BaseModel):
    phone: str = Field(..., min_length=6, max_length=32)
    purpose: str = Field(default="login", pattern=r"^(login|register)$")
    lot_number: str = Field(default="", max_length=256)
    captcha_output: str = Field(default="", max_length=4096)
    pass_token: str = Field(default="", max_length=4096)
    gen_time: str = Field(default="", max_length=64)


class PhoneCodeLoginRequest(BaseModel):
    phone: str = Field(..., min_length=6, max_length=32)
    code: str = Field(..., min_length=4, max_length=12)
    inviteCode: Optional[str] = Field(None, max_length=128)
    orgName: Optional[str] = Field(None, max_length=64)


class ProfileUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)


def _now() -> datetime:
    return datetime.utcnow()


def _client_ip_from_request(request: Request) -> str:
    forwarded_for = str(request.headers.get("x-forwarded-for") or "").strip()
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()[:128]
    real_ip = str(request.headers.get("x-real-ip") or "").strip()
    if real_ip:
        return real_ip[:128]
    return (request.client.host if request.client else "unknown")[:128]


def _normalize_email(value: str) -> str:
    email = str(value or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise ValueError("邮箱格式不正确")
    return email


def _normalize_phone(value: str) -> str:
    phone = re.sub(r"\D", "", str(value or ""))
    if phone.startswith("86") and len(phone) == 13:
        phone = phone[2:]
    if not CN_MOBILE_RE.match(phone):
        raise ValueError("手机号格式不正确")
    return phone


def _hash_email_code(email: str, purpose: str, code: str) -> str:
    settings = get_settings()
    payload = f"{email}:{purpose}:{code}".encode("utf-8")
    return hmac.new(settings.END_USER_AUTH_SECRET.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _hash_sms_code(phone: str, purpose: str, code: str) -> str:
    settings = get_settings()
    payload = f"{phone}:{purpose}:{code}".encode("utf-8")
    return hmac.new(settings.END_USER_AUTH_SECRET.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _generate_email_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _generate_sms_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


async def _ensure_email_verification_indexes() -> None:
    global _email_verification_indexes_ready
    if _email_verification_indexes_ready:
        return
    db = get_db()
    await db[EMAIL_VERIFICATION_COLLECTION].create_index(
        [("email", 1), ("purpose", 1), ("created_at", -1)],
        name="email_purpose_created_at",
    )
    await db[EMAIL_VERIFICATION_COLLECTION].create_index(
        [("ip", 1), ("created_at", -1)],
        name="ip_created_at",
    )
    await db[EMAIL_VERIFICATION_COLLECTION].create_index(
        [("expires_at", 1)],
        expireAfterSeconds=0,
        name="expires_at_ttl",
    )
    _email_verification_indexes_ready = True


async def _ensure_sms_verification_indexes() -> None:
    global _sms_verification_indexes_ready
    if _sms_verification_indexes_ready:
        return
    db = get_db()
    await db[SMS_VERIFICATION_COLLECTION].create_index(
        [("phone", 1), ("purpose", 1), ("created_at", -1)],
        name="phone_purpose_created_at",
    )
    await db[SMS_VERIFICATION_COLLECTION].create_index(
        [("ip", 1), ("created_at", -1)],
        name="ip_created_at",
    )
    await db[SMS_VERIFICATION_COLLECTION].create_index(
        [("expires_at", 1)],
        expireAfterSeconds=0,
        name="expires_at_ttl",
    )
    _sms_verification_indexes_ready = True


async def _check_email_code_send_limit(request: Request, email: str, purpose: str) -> ApiResponse | None:
    await _ensure_email_verification_indexes()
    db = get_db()
    now = _now()
    ip = _client_ip_from_request(request)
    email_recent = await db[EMAIL_VERIFICATION_COLLECTION].count_documents(
        {"email": email, "purpose": purpose, "created_at": {"$gte": now - timedelta(seconds=60)}}
    )
    if email_recent >= 1:
        return ApiResponse(code=1, message="验证码发送过于频繁，请稍后再试")
    email_hour = await db[EMAIL_VERIFICATION_COLLECTION].count_documents(
        {"email": email, "purpose": purpose, "created_at": {"$gte": now - timedelta(hours=1)}}
    )
    if email_hour >= 5:
        return ApiResponse(code=1, message="验证码发送次数过多，请稍后再试")
    ip_hour = await db[EMAIL_VERIFICATION_COLLECTION].count_documents(
        {"ip": ip, "created_at": {"$gte": now - timedelta(hours=1)}}
    )
    if ip_hour >= 30:
        return ApiResponse(code=1, message="验证码请求过于频繁，请稍后再试")
    return None


async def _check_sms_code_send_limit(request: Request, phone: str, purpose: str) -> ApiResponse | None:
    await _ensure_sms_verification_indexes()
    db = get_db()
    now = _now()
    ip = _client_ip_from_request(request)
    phone_recent = await db[SMS_VERIFICATION_COLLECTION].count_documents(
        {"phone": phone, "purpose": purpose, "created_at": {"$gte": now - timedelta(seconds=60)}}
    )
    if phone_recent >= 1:
        return ApiResponse(code=1, message="验证码发送过于频繁，请稍后再试")
    phone_hour = await db[SMS_VERIFICATION_COLLECTION].count_documents(
        {"phone": phone, "purpose": purpose, "created_at": {"$gte": now - timedelta(hours=1)}}
    )
    if phone_hour >= 5:
        return ApiResponse(code=1, message="验证码发送次数过多，请稍后再试")
    ip_hour = await db[SMS_VERIFICATION_COLLECTION].count_documents(
        {"ip": ip, "created_at": {"$gte": now - timedelta(hours=1)}}
    )
    if ip_hour >= 30:
        return ApiResponse(code=1, message="验证码请求过于频繁，请稍后再试")
    return None


def _aliyun_percent_encode(value: str) -> str:
    return quote(str(value), safe="~")


async def _verify_aliyun_captcha(payload: SmsVerificationRequest) -> bool:
    settings = get_settings()
    if not settings.ALIYUN_CAPTCHA_ENABLED:
        return True
    app_id = str(settings.ALIYUN_CAPTCHA_APP_ID or "").strip()
    app_key = str(settings.ALIYUN_CAPTCHA_APP_KEY or "").strip()
    domain = str(settings.ALIYUN_CAPTCHA_DOMAIN or "https://captcha.alicaptcha.com").rstrip("/")
    if not app_id or not app_key:
        raise RuntimeError("人机验证服务配置不完整")
    lot_number = str(payload.lot_number or "").strip()
    captcha_output = str(payload.captcha_output or "").strip()
    pass_token = str(payload.pass_token or "").strip()
    gen_time = str(payload.gen_time or "").strip()
    if not all((lot_number, captcha_output, pass_token, gen_time)):
        return False
    sign_token = hmac.new(
        app_key.encode("utf-8"),
        lot_number.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{domain}/validate",
            params={"captcha_id": app_id},
            data={
                "lot_number": lot_number,
                "captcha_output": captcha_output,
                "pass_token": pass_token,
                "gen_time": gen_time,
                "sign_token": sign_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    try:
        result = response.json()
    except Exception:
        result = {}
    if response.status_code >= 400:
        logger.warning("aliyun captcha request failed: status=%s body=%s", response.status_code, response.text[:300])
        return False
    verified = str(result.get("result") or "").lower() == "success"
    if not verified:
        logger.warning("aliyun captcha rejected: reason=%s", str(result.get("reason") or "unknown")[:300])
    return verified


async def _send_aliyun_sms(*, phone: str, code: str) -> None:
    settings = get_settings()
    access_key_id = str(settings.ALIYUN_SMS_ACCESS_KEY_ID or settings.OSS_ACCESS_KEY_ID or "").strip()
    access_key_secret = str(settings.ALIYUN_SMS_ACCESS_KEY_SECRET or settings.OSS_ACCESS_KEY_SECRET or "").strip()
    sign_name = str(settings.ALIYUN_SMS_SIGN_NAME or "").strip()
    template_code = str(settings.ALIYUN_SMS_TEMPLATE_CODE or "").strip()
    region_id = str(settings.ALIYUN_SMS_REGION_ID or "cn-hangzhou").strip()
    if not access_key_id:
        raise RuntimeError("短信服务未配置 ALIYUN_SMS_ACCESS_KEY_ID")
    if not access_key_secret:
        raise RuntimeError("短信服务未配置 ALIYUN_SMS_ACCESS_KEY_SECRET")
    if not sign_name:
        raise RuntimeError("短信服务未配置 ALIYUN_SMS_SIGN_NAME")
    if not template_code:
        raise RuntimeError("短信服务未配置 ALIYUN_SMS_TEMPLATE_CODE")

    params = {
        "Action": "SendSms",
        "Version": "2017-05-25",
        "RegionId": region_id,
        "Format": "JSON",
        "AccessKeyId": access_key_id,
        "SignatureMethod": "HMAC-SHA1",
        "SignatureVersion": "1.0",
        "SignatureNonce": str(uuid.uuid4()),
        "Timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "PhoneNumbers": phone,
        "SignName": sign_name,
        "TemplateCode": template_code,
        "TemplateParam": json.dumps({"code": code}, separators=(",", ":"), ensure_ascii=False),
    }
    canonical = "&".join(
        f"{_aliyun_percent_encode(key)}={_aliyun_percent_encode(params[key])}"
        for key in sorted(params)
    )
    string_to_sign = "POST&%2F&" + _aliyun_percent_encode(canonical)
    signature = base64.b64encode(
        hmac.new(
            (access_key_secret + "&").encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha1,
        ).digest()
    ).decode("utf-8")
    data = {**params, "Signature": signature}
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            "https://dysmsapi.aliyuncs.com/",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    try:
        payload = response.json()
    except Exception:
        payload = {}
    if response.status_code >= 400 or str(payload.get("Code") or "OK") != "OK":
        detail = str(payload.get("Message") or response.text or "unknown_error")
        raise RuntimeError(f"短信发送失败: {detail[:300]}")


def _send_aliyun_dm_email_sync(*, to_email: str, subject: str, text: str, html: str) -> None:
    settings = get_settings()
    host = str(settings.ALIYUN_DM_SMTP_HOST or "").strip()
    port = int(settings.ALIYUN_DM_SMTP_PORT or 465)
    username = str(settings.ALIYUN_DM_SMTP_USERNAME or "").strip()
    password = str(settings.ALIYUN_DM_SMTP_PASSWORD or "").strip()
    from_email = str(settings.ALIYUN_DM_FROM_EMAIL or username or "").strip()
    from_name = str(settings.ALIYUN_DM_FROM_NAME or "MOVO").strip()
    if not host:
        raise RuntimeError("邮件服务未配置 ALIYUN_DM_SMTP_HOST")
    if not username:
        raise RuntimeError("邮件服务未配置 ALIYUN_DM_SMTP_USERNAME")
    if not password:
        raise RuntimeError("邮件服务未配置 ALIYUN_DM_SMTP_PASSWORD")
    if not from_email:
        raise RuntimeError("邮件服务未配置 ALIYUN_DM_FROM_EMAIL")

    message = EmailMessage()
    message["From"] = formataddr((from_name, from_email))
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(text)
    message.add_alternative(html, subtype="html")

    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=15) as smtp:
            smtp.login(username, password)
            smtp.send_message(message, from_addr=from_email, to_addrs=[to_email])
    else:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.starttls()
            smtp.login(username, password)
            smtp.send_message(message, from_addr=from_email, to_addrs=[to_email])


async def _send_aliyun_dm_email(*, to_email: str, subject: str, text: str, html: str) -> None:
    try:
        await asyncio.to_thread(
            _send_aliyun_dm_email_sync,
            to_email=to_email,
            subject=subject,
            text=text,
            html=html,
        )
    except smtplib.SMTPResponseException as exc:
        detail = exc.smtp_error.decode("utf-8", errors="ignore") if isinstance(exc.smtp_error, bytes) else str(exc.smtp_error)
        raise RuntimeError(f"邮件发送失败: {exc.smtp_code} {detail}") from exc
    except smtplib.SMTPException as exc:
        raise RuntimeError(f"邮件发送失败: {exc}") from exc


async def _create_and_send_email_code(request: Request, email: str, purpose: str) -> ApiResponse:
    limited = await _check_email_code_send_limit(request, email, purpose)
    if limited is not None:
        return limited
    db = get_db()
    now = _now()
    settings = get_settings()
    ttl = max(60, int(settings.EMAIL_VERIFICATION_CODE_TTL_SECONDS or 600))
    code = _generate_email_code()
    purpose_label = "注册" if purpose == "register" else "重置密码"
    await db[EMAIL_VERIFICATION_COLLECTION].insert_one(
        {
            "email": email,
            "purpose": purpose,
            "code_hash": _hash_email_code(email, purpose, code),
            "status": "active",
            "attempts": 0,
            "ip": _client_ip_from_request(request),
            "user_agent": str(request.headers.get("user-agent") or "")[:500],
            "created_at": now,
            "expires_at": now + timedelta(seconds=ttl),
        }
    )
    text = f"你的 MOVO {purpose_label}验证码是：{code}。验证码 {ttl // 60} 分钟内有效。"
    html = (
        "<div style=\"font-family:Arial,sans-serif;line-height:1.6;color:#0f172a\">"
        f"<p>你的 MOVO {purpose_label}验证码是：</p>"
        f"<p style=\"font-size:28px;font-weight:700;letter-spacing:6px\">{code}</p>"
        f"<p>验证码 {ttl // 60} 分钟内有效。如果不是你本人操作，请忽略这封邮件。</p>"
        "</div>"
    )
    await _send_aliyun_dm_email(to_email=email, subject=f"MOVO {purpose_label}验证码", text=text, html=html)
    return ApiResponse(code=0, message="验证码已发送")


async def _create_and_send_sms_code(request: Request, phone: str, purpose: str) -> ApiResponse:
    limited = await _check_sms_code_send_limit(request, phone, purpose)
    if limited is not None:
        return limited
    db = get_db()
    now = _now()
    settings = get_settings()
    ttl = max(60, int(settings.SMS_VERIFICATION_CODE_TTL_SECONDS or 300))
    code = _generate_sms_code()
    await db[SMS_VERIFICATION_COLLECTION].insert_one(
        {
            "phone": phone,
            "purpose": purpose,
            "code_hash": _hash_sms_code(phone, purpose, code),
            "status": "active",
            "attempts": 0,
            "ip": _client_ip_from_request(request),
            "user_agent": str(request.headers.get("user-agent") or "")[:500],
            "created_at": now,
            "expires_at": now + timedelta(seconds=ttl),
        }
    )
    await _send_aliyun_sms(phone=phone, code=code)
    return ApiResponse(code=0, message="验证码已发送")


async def _verify_email_code(email: str, purpose: str, code: str, *, consume: bool) -> bool:
    await _ensure_email_verification_indexes()
    db = get_db()
    now = _now()
    doc = await db[EMAIL_VERIFICATION_COLLECTION].find_one(
        {
            "email": email,
            "purpose": purpose,
            "status": "active",
            "expires_at": {"$gte": now},
        },
        sort=[("created_at", -1)],
    )
    if not doc:
        return False
    attempts = int(doc.get("attempts") or 0)
    if attempts >= 5:
        await db[EMAIL_VERIFICATION_COLLECTION].update_one(
            {"_id": doc["_id"]},
            {"$set": {"status": "failed", "updated_at": now}},
        )
        return False
    expected = str(doc.get("code_hash") or "")
    actual = _hash_email_code(email, purpose, str(code or "").strip())
    if not hmac.compare_digest(expected, actual):
        await db[EMAIL_VERIFICATION_COLLECTION].update_one(
            {"_id": doc["_id"]},
            {"$inc": {"attempts": 1}, "$set": {"updated_at": now}},
        )
        return False
    if consume:
        await db[EMAIL_VERIFICATION_COLLECTION].update_one(
            {"_id": doc["_id"]},
            {"$set": {"status": "used", "used_at": now, "updated_at": now}},
        )
    return True


async def _verify_sms_code(phone: str, purpose: str, code: str, *, consume: bool) -> bool:
    await _ensure_sms_verification_indexes()
    db = get_db()
    now = _now()
    doc = await db[SMS_VERIFICATION_COLLECTION].find_one(
        {
            "phone": phone,
            "purpose": purpose,
            "status": "active",
            "expires_at": {"$gte": now},
        },
        sort=[("created_at", -1)],
    )
    if not doc:
        return False
    attempts = int(doc.get("attempts") or 0)
    if attempts >= 5:
        await db[SMS_VERIFICATION_COLLECTION].update_one(
            {"_id": doc["_id"]},
            {"$set": {"status": "failed", "updated_at": now}},
        )
        return False
    expected = str(doc.get("code_hash") or "")
    actual = _hash_sms_code(phone, purpose, str(code or "").strip())
    if not hmac.compare_digest(expected, actual):
        await db[SMS_VERIFICATION_COLLECTION].update_one(
            {"_id": doc["_id"]},
            {"$inc": {"attempts": 1}, "$set": {"updated_at": now}},
        )
        return False
    if consume:
        await db[SMS_VERIFICATION_COLLECTION].update_one(
            {"_id": doc["_id"]},
            {"$set": {"status": "used", "used_at": now, "updated_at": now}},
        )
    return True


async def _ensure_registration_attempt_indexes() -> None:
    global _registration_attempt_indexes_ready
    if _registration_attempt_indexes_ready:
        return
    db = get_db()
    await db[REGISTRATION_ATTEMPT_COLLECTION].create_index(
        [("ip", 1), ("created_at", -1)],
        name="ip_created_at",
    )
    await db[REGISTRATION_ATTEMPT_COLLECTION].create_index(
        "created_at",
        expireAfterSeconds=3 * 24 * 60 * 60,
        name="created_at_ttl",
    )
    _registration_attempt_indexes_ready = True


async def _record_registration_attempt(
    *,
    request: Request,
    payload: dict[str, Any],
    blocked: bool,
    reason: str = "",
) -> None:
    await _ensure_registration_attempt_indexes()
    db = get_db()
    invite_code = str(payload.get("inviteCode") or "").strip()
    await db[REGISTRATION_ATTEMPT_COLLECTION].insert_one(
        {
            "ip": _client_ip_from_request(request),
            "username": str(payload.get("username") or "").strip()[:128],
            "has_invite_code": bool(invite_code),
            "invite_code_prefix": invite_code[:12],
            "blocked": bool(blocked),
            "reason": str(reason or "")[:200],
            "user_agent": str(request.headers.get("user-agent") or "")[:500],
            "created_at": _now(),
        }
    )


async def _check_registration_rate_limit(request: Request, payload: dict[str, Any]) -> ApiResponse | None:
    await _ensure_registration_attempt_indexes()
    db = get_db()
    now = _now()
    ip = _client_ip_from_request(request)
    invite_code = str(payload.get("inviteCode") or "").strip()
    limits = (
        [(60, 5), (60 * 60, 30), (24 * 60 * 60, 100)]
        if invite_code
        else [(60, 2), (60 * 60, 10), (24 * 60 * 60, 30)]
    )
    for seconds, max_count in limits:
        count = await db[REGISTRATION_ATTEMPT_COLLECTION].count_documents(
            {
                "ip": ip,
                "created_at": {"$gte": now - timedelta(seconds=seconds)},
            }
        )
        if count >= max_count:
            await _record_registration_attempt(
                request=request,
                payload=payload,
                blocked=True,
                reason=f"rate_limit:{seconds}s:{max_count}",
            )
            return ApiResponse(code=1, message="注册请求过于频繁，请稍后再试")
    await _record_registration_attempt(request=request, payload=payload, blocked=False)
    return None


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


@router.post("/auth/email-code", response_model=ApiResponse)
async def send_email_code(payload: EmailVerificationRequest, request: Request) -> ApiResponse:
    try:
        email = _normalize_email(payload.email)
    except ValueError as exc:
        return ApiResponse(code=1, message=str(exc))
    purpose = payload.purpose
    if purpose == "password_reset":
        db = get_db()
        exists = await db[USER_COLLECTION].find_one({"email": email, "status": "active"})
        if not exists:
            return ApiResponse(code=1, message="该邮箱尚未绑定账号")
    try:
        return await _create_and_send_email_code(request, email, purpose)
    except Exception as exc:
        return ApiResponse(code=1, message=str(exc))


@router.post("/auth/sms-code", response_model=ApiResponse)
async def send_sms_code(payload: SmsVerificationRequest, request: Request) -> ApiResponse:
    try:
        phone = _normalize_phone(payload.phone)
    except ValueError as exc:
        return ApiResponse(code=1, message=str(exc))
    try:
        if not await _verify_aliyun_captcha(payload):
            return ApiResponse(code=1, message="请先完成人机验证")
        return await _create_and_send_sms_code(request, phone, payload.purpose)
    except Exception as exc:
        logger.warning("sms code send failed: phone=%s purpose=%s error=%s", phone, payload.purpose, exc)
        return ApiResponse(code=1, message="短信验证码发送失败，请稍后再试")


@router.get("/auth/captcha-config", response_model=ApiResponse)
async def get_captcha_config() -> ApiResponse:
    settings = get_settings()
    return ApiResponse(
        code=0,
        data={
            "enabled": bool(settings.ALIYUN_CAPTCHA_ENABLED),
            "captchaId": str(settings.ALIYUN_CAPTCHA_APP_ID or "").strip(),
        },
    )


@router.post("/auth/phone-login", response_model=ApiResponse)
async def phone_login(payload: PhoneCodeLoginRequest, request: Request) -> ApiResponse:
    try:
        phone = _normalize_phone(payload.phone)
    except ValueError as exc:
        return ApiResponse(code=1, message=str(exc))
    ok = await _verify_sms_code(phone, "login", payload.code, consume=True)
    if not ok:
        return ApiResponse(code=1, message="验证码错误或已过期")

    db = get_db()
    invite_code = str(payload.inviteCode or "").strip()
    requested_org_name = str(payload.orgName or "").strip()
    if invite_code and requested_org_name:
        return ApiResponse(code=1, message="创建企业和加入企业不能同时选择")

    if requested_org_name:
        if await _check_org_name_duplicate(requested_org_name):
            return ApiResponse(
                code=1,
                message=_t(
                    request,
                    "该企业名称已被注册，请更换",
                    "The enterprise name is already registered, please choose another name."
                )
            )

    users = await db[USER_COLLECTION].find({"mobile": phone, "status": "active"}).to_list(length=200)
    invite_doc: dict[str, Any] | None = None
    default_department_id = ""
    if invite_code:
        invite_doc = await db[USER_INVITE_COLLECTION].find_one({"token": invite_code, "status": "active"})
        if not invite_doc:
            return ApiResponse(code=1, message="邀请码不存在或已失效")
        if invite_doc.get("expires_at") and invite_doc["expires_at"] < _now():
            await db[USER_INVITE_COLLECTION].update_one(
                {"_id": invite_doc["_id"]},
                {"$set": {"status": "expired", "updated_at": _now()}},
            )
            return ApiResponse(code=1, message="邀请码已过期")
        invite_main_id = resolve_main_id(invite_doc.get("main_id"))
        if not _is_valid_tenant_main_id(invite_main_id):
            return ApiResponse(code=1, message="邀请码所属组织无效，请联系管理员重新生成")
        default_department_id = str(invite_doc.get("default_department_id") or "").strip()

    if users:
        if requested_org_name:
            base_user = users[0]
            username = str(base_user.get("login_name") or phone)
            main_id = f"org_{uuid.uuid4().hex[:12]}"
            now = _now()
            new_user = {
                "login_name": username,
                "name": str(base_user.get("name") or username),
                **_avatar_fields_from_user(base_user),
                "space_type": "enterprise",
                "mobile": phone,
                "mobile_verified": True,
                "mobile_verified_at": base_user.get("mobile_verified_at") or now,
                "email": str(base_user.get("email") or ""),
                "email_verified": bool(base_user.get("email_verified") or False),
                "email_verified_at": base_user.get("email_verified_at"),
                "password_hash": str(base_user.get("password_hash") or ""),
                "password_salt": str(base_user.get("password_salt") or ""),
                "main_id": main_id,
                "org_name": requested_org_name,
                "source": "local",
                "source_user_id": "",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
            try:
                result = await db[USER_COLLECTION].insert_one(new_user)
                user_id = str(result.inserted_id)
            except DuplicateKeyError:
                return ApiResponse(code=1, message="企业创建失败，请稍后再试")

            await db[ADMIN_ACCOUNT_COLLECTION].insert_one(
                {
                    "main_id": main_id,
                    "username": username,
                    "display_name": str(base_user.get("name") or username),
                    "email": str(base_user.get("email") or ""),
                    "phone": phone,
                    "group_code": "admin",
                    "role_name": "平台超级管理员",
                    "org_name": requested_org_name,
                    "status": "active",
                    "is_protected": True,
                    "password_hash": str(base_user.get("password_hash") or ""),
                    "password_salt": str(base_user.get("password_salt") or ""),
                    "last_login_at": None,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            from app.core.billing import init_organization_quota

            await init_organization_quota(main_id=main_id, org_name=requested_org_name, owner_id=user_id, total_points=0)
            primary_department_id = await _ensure_root_department(main_id)
            await _assign_user_primary_department(main_id, user_id, primary_department_id)
            candidates = await _load_available_tenants(username)
            session_payload = await _create_session(new_user, candidates)
            return ApiResponse(code=0, message="登录成功，已创建企业", data=session_payload)

        if invite_doc:
            main_id = resolve_main_id(invite_doc.get("main_id"))
            org_name = str(invite_doc.get("org_name") or "").strip() or "组织空间"
            existing_target = next(
                (item for item in users if resolve_main_id(item.get("main_id")) == main_id),
                None,
            )
            if existing_target:
                candidates = await _load_available_tenants(str(existing_target.get("login_name") or phone))
                fallback = await load_tenant_candidates(db, [existing_target])
                session_payload = await _create_session(existing_target, candidates or fallback)
                return ApiResponse(code=0, message="登录成功", data=session_payload)

            base_user = users[0]
            username = str(base_user.get("login_name") or phone)
            now = _now()
            new_user = {
                "login_name": username,
                "name": str(base_user.get("name") or username),
                **_avatar_fields_from_user(base_user),
                "space_type": "enterprise",
                "mobile": phone,
                "mobile_verified": True,
                "mobile_verified_at": base_user.get("mobile_verified_at") or now,
                "email": str(base_user.get("email") or ""),
                "email_verified": bool(base_user.get("email_verified") or False),
                "email_verified_at": base_user.get("email_verified_at"),
                "password_hash": str(base_user.get("password_hash") or ""),
                "password_salt": str(base_user.get("password_salt") or ""),
                "main_id": main_id,
                "org_name": org_name,
                "source": "local",
                "source_user_id": "",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
            try:
                result = await db[USER_COLLECTION].insert_one(new_user)
                user_id = str(result.inserted_id)
            except DuplicateKeyError:
                existing_target = await db[USER_COLLECTION].find_one({"login_name": username, "main_id": main_id, "status": "active"})
                if not existing_target:
                    return ApiResponse(code=1, message="加入企业失败，请稍后再试")
                candidates = await _load_available_tenants(username)
                fallback = await load_tenant_candidates(db, [existing_target])
                session_payload = await _create_session(existing_target, candidates or fallback)
                return ApiResponse(code=0, message="登录成功", data=session_payload)

            primary_department_id = await _resolve_primary_department(main_id, default_department_id or None)
            await _assign_user_primary_department(main_id, user_id, primary_department_id)
            await db[USER_INVITE_COLLECTION].update_one(
                {"_id": invite_doc["_id"]},
                {"$set": {"status": "used", "used_at": now, "updated_at": now, "user_id": user_id}},
            )
            candidates = await _load_available_tenants(username)
            session_payload = await _create_session(new_user, candidates)
            return ApiResponse(code=0, message="登录成功，已加入企业", data=session_payload)

        candidates = await load_tenant_candidates(db, users)
        valid_candidates = [item for item in candidates if _is_valid_tenant_main_id(resolve_main_id(item.get("mainId")))]
        if len(valid_candidates) > 1:
            challenge = await _create_login_challenge(phone, valid_candidates)
            return ApiResponse(
                code=0,
                message="请选择组织",
                data={
                    "requiresTenantSelection": True,
                    "challengeToken": challenge["challengeToken"],
                    "candidates": valid_candidates,
                },
            )
        user_doc = users[0]
        fallback = await load_tenant_candidates(db, [user_doc])
        session_payload = await _create_session(user_doc, valid_candidates or fallback)
        return ApiResponse(code=0, data=session_payload)

    main_id = ""
    org_name = ""
    admin_group_code = "admin"
    admin_role_name = "平台超级管理员"
    admin_is_protected = True
    if invite_code:
        main_id = resolve_main_id(invite_doc.get("main_id"))
        org_name = str(invite_doc.get("org_name") or "").strip() or "组织空间"
        admin_group_code = "member"
        admin_role_name = "普通成员"
        admin_is_protected = False
    else:
        main_id = f"org_{uuid.uuid4().hex[:12]}"
        org_name = requested_org_name or "个人空间"

    from app.core.end_user_auth import hash_password

    random_password = secrets.token_urlsafe(24)
    pw_hash, pw_salt = hash_password(random_password)
    now = _now()
    new_user = {
        "login_name": phone,
        "name": phone,
        "space_type": "enterprise" if invite_code or requested_org_name else "personal",
        "mobile": phone,
        "mobile_verified": True,
        "mobile_verified_at": now,
        "password_hash": pw_hash,
        "password_salt": pw_salt,
        "main_id": main_id,
        "org_name": org_name,
        "source": "local",
        "source_user_id": "",
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    try:
        result = await db[USER_COLLECTION].insert_one(new_user)
        user_id = str(result.inserted_id)
    except DuplicateKeyError:
        return ApiResponse(code=1, message="该手机号已注册，请直接登录")

    admin_user = {
        "main_id": main_id,
        "username": phone,
        "display_name": phone,
        "email": "",
        "phone": phone,
        "group_code": admin_group_code,
        "role_name": admin_role_name,
        "org_name": org_name,
        "status": "active",
        "is_protected": admin_is_protected,
        "password_hash": pw_hash,
        "password_salt": pw_salt,
        "last_login_at": None,
        "created_at": now,
        "updated_at": now,
    }
    if admin_group_code != "member":
        await db[ADMIN_ACCOUNT_COLLECTION].insert_one(admin_user)
    primary_department_id = await _resolve_primary_department(main_id, default_department_id or None)
    await _assign_user_primary_department(main_id, user_id, primary_department_id)
    if not invite_doc:
        from app.core.billing import init_organization_quota

        gift_points = 0 if requested_org_name else 1000000
        await init_organization_quota(main_id=main_id, org_name=org_name, owner_id=user_id, total_points=gift_points)
    else:
        await db[USER_INVITE_COLLECTION].update_one(
            {"_id": invite_doc["_id"]},
            {"$set": {"status": "used", "used_at": now, "updated_at": now, "user_id": user_id}},
        )
    candidates = await _load_available_tenants(phone)
    session_payload = await _create_session(new_user, candidates)
    return ApiResponse(code=0, message="登录成功", data=session_payload)


@router.post("/auth/password-reset/confirm", response_model=ApiResponse)
async def confirm_password_reset(payload: PasswordResetConfirmRequest) -> ApiResponse:
    try:
        email = _normalize_email(payload.email)
    except ValueError as exc:
        return ApiResponse(code=1, message=str(exc))
    ok = await _verify_email_code(email, "password_reset", payload.code, consume=True)
    if not ok:
        return ApiResponse(code=1, message="验证码错误或已过期")
    db = get_db()
    users = await db[USER_COLLECTION].find({"email": email, "status": "active"}).to_list(length=200)
    if not users:
        return ApiResponse(code=1, message="该邮箱尚未绑定账号")
    from app.core.end_user_auth import hash_password

    pw_hash, pw_salt = hash_password(payload.newPassword)
    now = _now()
    user_ids = [item["_id"] for item in users]
    usernames = sorted({str(item.get("login_name") or "") for item in users if item.get("login_name")})
    await db[USER_COLLECTION].update_many(
        {"_id": {"$in": user_ids}},
        {"$set": {"password_hash": pw_hash, "password_salt": pw_salt, "updated_at": now}},
    )
    await db[ADMIN_ACCOUNT_COLLECTION].update_many(
        {"email": email, "status": "active"},
        {"$set": {"password_hash": pw_hash, "password_salt": pw_salt, "updated_at": now}},
    )
    await db[USER_SESSION_COLLECTION].update_many(
        {"user_id": {"$in": [str(item) for item in user_ids]}, "status": "active"},
        {"$set": {"status": "revoked", "updated_at": now}},
    )
    return ApiResponse(
        code=0,
        message="密码已重置，请重新登录",
        data={"usernames": usernames},
    )


# ==========================================
# 计费与多组织（SSO）管理新增接口
# ==========================================

import time
import uuid
import os
import json
import base64
import hmac
import hashlib

ADMIN_ACCOUNT_COLLECTION = "admin_accounts"
ADMIN_SESSION_COLLECTION = "admin_sessions"
USER_INVITE_COLLECTION = "user_invites"
USER_ORG_REL_COLLECTION = "end_user_org_relations"
DEPARTMENT_COLLECTION = "org_units"


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)
    email: str = Field(..., min_length=3, max_length=254)
    emailCode: str = Field(..., min_length=4, max_length=12)
    displayName: Optional[str] = Field(None, max_length=64)
    orgName: Optional[str] = Field(None, max_length=64)
    inviteCode: Optional[str] = Field(None, max_length=128)


class CreateOrgRequest(BaseModel):
    orgName: str = Field(..., min_length=1, max_length=64)


class RenameOrgRequest(BaseModel):
    orgName: str = Field(..., min_length=1, max_length=64)


class AddMemberRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)
    displayName: Optional[str] = Field(None, max_length=64)


class UpgradeRequest(BaseModel):
    tier: str = Field(..., pattern=r"^(plus|pro|enterprise)$")


class BillingOrderRequest(BaseModel):
    planCode: str = Field(..., min_length=2, max_length=64)
    paymentMethod: str = Field(default="wechat_native", pattern=r"^(wechat_native|wechat_jsapi|wechat_h5|dev_mock)$")


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


@router.post("/auth/register", response_model=ApiResponse)
async def register(payload: RegisterRequest, request: Request) -> ApiResponse:
    limited = await _check_registration_rate_limit(request, payload.model_dump())
    if limited is not None:
        return limited

    db = get_db()
    invite_code = str(payload.inviteCode or "").strip()
    username = payload.username.strip()
    try:
        email = _normalize_email(payload.email)
    except ValueError as exc:
        return ApiResponse(code=1, message=str(exc))
    email_ok = await _verify_email_code(email, "register", payload.emailCode, consume=True)
    if not email_ok:
        return ApiResponse(code=1, message="邮箱验证码错误或已过期")

    main_id = ""
    org_name = ""
    default_department_id = ""
    admin_group_code = "admin"
    admin_role_name = "平台超级管理员"
    admin_is_protected = True
    invite_doc: dict[str, Any] | None = None

    if invite_code:
        invite_doc = await db[USER_INVITE_COLLECTION].find_one({"token": invite_code, "status": "active"})
        if not invite_doc:
            return ApiResponse(code=1, message="邀请码不存在或已失效")
        if invite_doc.get("expires_at") and invite_doc["expires_at"] < _now():
            await db[USER_INVITE_COLLECTION].update_one(
                {"_id": invite_doc["_id"]},
                {"$set": {"status": "expired", "updated_at": _now()}},
            )
            return ApiResponse(code=1, message="邀请码已过期")
        main_id = resolve_main_id(invite_doc.get("main_id"))
        if not _is_valid_tenant_main_id(main_id):
            return ApiResponse(code=1, message="邀请码所属组织无效，请联系管理员重新生成")
        org_name = str(invite_doc.get("org_name") or "").strip() or "组织空间"
        default_department_id = str(invite_doc.get("default_department_id") or "").strip()
        admin_group_code = "member"
        admin_role_name = "普通成员"
    else:
        main_id = f"org_{uuid.uuid4().hex[:12]}"
        org_name = (payload.orgName or "").strip() or "个人空间"
        if org_name != "个人空间":
            if await _check_org_name_duplicate(org_name):
                return ApiResponse(
                    code=1,
                    message=_t(
                        request,
                        "该企业名称已被注册，请更换",
                        "The enterprise name is already registered, please choose another name."
                    )
                )

    from app.core.end_user_auth import hash_password
    pw_hash, pw_salt = hash_password(payload.password)

    # 1. 写入用户端用户
    new_user = {
        "login_name": username,
        "name": (payload.displayName or "").strip() or username,
        "space_type": "enterprise" if invite_doc or (payload.orgName or "").strip() else "personal",
        "email": email,
        "email_verified": True,
        "email_verified_at": _now(),
        "password_hash": pw_hash,
        "password_salt": pw_salt,
        "main_id": main_id,
        "org_name": org_name,
        "source": "local",
        "source_user_id": "",
        "status": "active",
        "created_at": _now(),
        "updated_at": _now(),
    }

    try:
        result = await db[USER_COLLECTION].insert_one(new_user)
        user_id = str(result.inserted_id)
    except DuplicateKeyError:
        if invite_code:
            return ApiResponse(code=1, message="该登录名在当前组织中已存在")
        return ApiResponse(code=1, message="注册失败，当前组织内登录名已存在")
    except Exception as exc:
        return ApiResponse(code=1, message=f"注册失败，可能用户名已存在: {exc}")

    # 2. 写入后台超管账户
    admin_user = {
        "main_id": main_id,
        "username": username,
        "display_name": (payload.displayName or "").strip() or username,
        "email": email,
        "phone": "",
        "group_code": admin_group_code,
        "role_name": admin_role_name,
        "org_name": org_name,
        "status": "active",
        "is_protected": admin_is_protected,
        "password_hash": pw_hash,
        "password_salt": pw_salt,
        "last_login_at": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    if admin_group_code != "member":
        await db[ADMIN_ACCOUNT_COLLECTION].insert_one(admin_user)

    # 3. 初始化组织架构与默认部门关系
    primary_department_id = await _resolve_primary_department(main_id, default_department_id or None)
    await _assign_user_primary_department(main_id, user_id, primary_department_id)

    # 4. 仅在自主注册时初始化默认组织配额；邀请码注册直接加入现有组织
    if not invite_doc:
        from app.core.billing import init_organization_quota

        gift_points = 1000000 if org_name == "个人空间" else 0
        await init_organization_quota(main_id=main_id, org_name=org_name, owner_id=user_id, total_points=gift_points)
    else:
        await db[USER_INVITE_COLLECTION].update_one(
            {"_id": invite_doc["_id"]},
            {"$set": {"status": "used", "used_at": _now(), "updated_at": _now(), "user_id": user_id}},
        )

    # 5. 自动生成会话并登录
    candidates = await _load_available_tenants(username)
    session_payload = await _create_session(new_user, candidates)
    message = "注册成功，已加入组织" if invite_doc else "注册并初始化空间成功"
    return ApiResponse(code=0, message=message, data=session_payload)


@router.post("/organizations/create", response_model=ApiResponse)
async def create_organization(
    payload: CreateOrgRequest,
    request: Request,
    authorization: str | None = Header(default=None)
) -> ApiResponse:
    resolved = await _resolve_session_user(authorization)
    current_user = resolved["user"]
    if resolve_space_type(current_user) != "personal":
        return ApiResponse(
            code=1,
            message=_t(
                request,
                "企业成员不能在企业空间内创建新企业，请先切换到个人空间",
                "Enterprise members cannot create an organization from an enterprise space. Switch to a personal space first.",
            ),
        )
    
    db = get_db()
    
    # 生成新主组织 ID
    new_main_id = f"org_{uuid.uuid4().hex[:12]}"
    org_name = payload.orgName.strip()
    username = current_user["login_name"]
    
    if await _check_org_name_duplicate(org_name):
        return ApiResponse(
            code=1,
            message=_t(
                request,
                "该企业名称已被注册，请更换",
                "The enterprise name is already registered, please choose another name."
            )
        )

    # 检查在此新 main_id 下，是否已存在同名账号（防重）
    existing = await db[USER_COLLECTION].find_one({"login_name": username, "main_id": new_main_id})
    if existing:
        return ApiResponse(code=1, message="新组织ID冲突，请重试")
    # 1. 在新 main_id 空间下插入当前用户记录 (无缝密码同步)
    new_user = {
        "login_name": username,
        "name": current_user["name"],
        **_avatar_fields_from_user(current_user),
        "space_type": "enterprise",
        "mobile": current_user.get("mobile") or "",
        "mobile_verified": bool(current_user.get("mobile_verified") or False),
        "mobile_verified_at": current_user.get("mobile_verified_at"),
        "email": current_user.get("email") or "",
        "email_verified": bool(current_user.get("email_verified") or False),
        "email_verified_at": current_user.get("email_verified_at"),
        "password_hash": current_user["password_hash"],
        "password_salt": current_user["password_salt"],
        "main_id": new_main_id,
        "org_name": org_name,
        "source": "local",
        "source_user_id": "",
        "status": "active",
        "created_at": _now(),
        "updated_at": _now(),
    }
    result = await db[USER_COLLECTION].insert_one(new_user)
    user_id = str(result.inserted_id)
    
    # 2. 同步写入后台超管账号到新 main_id 空间
    admin_user = {
        "main_id": new_main_id,
        "username": username,
        "display_name": current_user["name"],
        "email": current_user.get("email") or "",
        "phone": current_user.get("mobile") or "",
        "group_code": "admin",
        "role_name": "平台超级管理员",
        "org_name": org_name,
        "status": "active",
        "is_protected": True,
        "password_hash": current_user["password_hash"],
        "password_salt": current_user["password_salt"],
        "last_login_at": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db[ADMIN_ACCOUNT_COLLECTION].insert_one(admin_user)
    
    # 3. 初始化新组织的 Quota 配置
    from app.core.billing import init_organization_quota
    await init_organization_quota(main_id=new_main_id, org_name=org_name, owner_id=user_id, total_points=0)

    primary_department_id = await _ensure_root_department(new_main_id)
    await _assign_user_primary_department(new_main_id, user_id, primary_department_id)

    # 4. 获取当前用户所有可用组织，并刷新 Session 使得前端能够识别
    candidates = await _load_available_tenants(username)
    session_payload = await _create_session(new_user, candidates)
    return ApiResponse(code=0, message="创建新组织成功", data=session_payload)


@router.post("/organizations/rename", response_model=ApiResponse)
async def rename_organization(
    payload: RenameOrgRequest,
    authorization: str | None = Header(default=None)
) -> ApiResponse:
    resolved = await _resolve_session_user(authorization)
    main_id = resolved["main_id"]
    current_user = resolved["user"]
    
    db = get_db()
    org_name = payload.orgName.strip()
    
    # 1. 修改 organizations 集合记录
    from app.core.billing import get_or_create_organization
    org = await get_or_create_organization(main_id)
    if str(org.get("owner_user_id")) != str(current_user["_id"]):
        return ApiResponse(code=1, message="只有组织创建者才能重命名空间")
        
    await db["organizations"].update_one(
        {"main_id": main_id},
        {"$set": {"org_name": org_name, "updated_at": _now()}}
    )
    
    # 2. 同步更新当前 main_id 下所有用户的 org_name
    await db[USER_COLLECTION].update_many(
        {"main_id": main_id},
        {"$set": {"org_name": org_name, "updated_at": _now()}}
    )
    
    # 3. 同步更新后台账号中该 main_id 的 org_name
    await db[ADMIN_ACCOUNT_COLLECTION].update_many(
        {"main_id": main_id},
        {"$set": {"org_name": org_name, "updated_at": _now()}}
    )
    
    # 4. 重新获取该用户下可用的租户列表，更新前端 profile
    users_rows = await db[USER_COLLECTION].find({"login_name": current_user["login_name"], "status": "active"}).to_list(length=200)
    candidates = await load_tenant_candidates(db, users_rows)
    session_payload = await _create_session(resolved["user"], candidates)
    
    return ApiResponse(code=0, message="重命名组织成功", data=session_payload)


@router.post("/organizations/add-member", response_model=ApiResponse)
async def add_member(
    payload: AddMemberRequest,
    authorization: str | None = Header(default=None)
) -> ApiResponse:
    resolved = await _resolve_session_user(authorization)
    main_id = resolved["main_id"]
    current_user = resolved["user"]
    
    db = get_db()
    username = payload.username.strip()

    from app.core.billing import get_or_create_organization
    org = await get_or_create_organization(main_id)
    if str(org.get("owner_user_id") or "") != str(current_user.get("_id") or ""):
        return ApiResponse(code=1, message="只有组织创建者才能添加成员")
    
    # 1. 判断当前组织人数是否超限
    from app.core.billing import check_member_limit
    try:
        await check_member_limit(main_id)
    except ValueError as val_err:
        return ApiResponse(code=1, message=str(val_err))
        
    # 2. 检查此组织内是否已存在该账号
    existing = await db[USER_COLLECTION].find_one({"main_id": main_id, "login_name": username})
    if existing:
        return ApiResponse(code=1, message="该用户名在当前组织中已存在")
        
    # 3. 生成新账户并加密密码
    from app.core.end_user_auth import hash_password
    pw_hash, pw_salt = hash_password(payload.password)
    
    org_name = current_user.get("org_name") or "个人空间"
    
    new_user = {
        "login_name": username,
        "name": (payload.displayName or "").strip() or username,
        "space_type": "enterprise",
        "password_hash": pw_hash,
        "password_salt": pw_salt,
        "main_id": main_id,
        "org_name": org_name,
        "source": "local",
        "source_user_id": "",
        "status": "active",
        "created_at": _now(),
        "updated_at": _now(),
    }
    result = await db[USER_COLLECTION].insert_one(new_user)
    user_id = str(result.inserted_id)

    primary_department_id = await _ensure_root_department(main_id)
    await _assign_user_primary_department(main_id, user_id, primary_department_id)

    
    return ApiResponse(code=0, message="添加成员成功", data={"username": username, "userId": user_id})


@router.post("/organizations/upgrade", response_model=ApiResponse)
async def upgrade(
    payload: UpgradeRequest,
    authorization: str | None = Header(default=None)
) -> ApiResponse:
    resolved = await _resolve_session_user(authorization)
    main_id = resolved["main_id"]
    current_user = resolved["user"]

    if resolve_space_type(current_user) != "personal":
        return ApiResponse(code=1, message="企业空间不能在用户端升级套餐，请联系企业管理员")

    from app.core.billing import create_billing_order, get_or_create_organization, mark_order_paid_and_apply
    org = await get_or_create_organization(main_id)

    if str(org.get("owner_user_id")) != str(current_user["_id"]):
        return ApiResponse(code=1, message="只有组织创建者才能升级订阅套餐")

    if not get_settings().ENABLE_DEV_BILLING:
        return ApiResponse(code=1, message="当前部署未启用在线套餐升级")

    tier = payload.tier
    if tier == "enterprise":
        return ApiResponse(
            code=0,
            message="企业版定制需求已提交，商务人员将在 24 小时内联系您进行详细方案对接。"
        )
    plan_code = "personal_plus_monthly" if tier == "plus" else "org_pro_monthly"
    try:
        order = await create_billing_order(
            main_id=main_id,
            buyer_user_id=str(current_user["_id"]),
            plan_code=plan_code,
            source="frontend_legacy_upgrade",
            payment_method="dev_mock",
        )
        applied = await mark_order_paid_and_apply(main_id, str(order["orderNo"]))
    except ValueError as exc:
        return ApiResponse(code=1, message=str(exc))

    if tier == "plus":
        return ApiResponse(
            code=0,
            message="成功升级为个人 Plus 尊享版！共享点数扩展为 20,000,000 点，并且支持配置自建模型。",
            data={"order": applied},
        )
    return ApiResponse(
        code=0,
        message="成功升级为专业团队版！团队人数上限已提升至 50 人，您现在可以前往管理后台配置并绑定您团队的专属模型密钥。",
        data={"order": applied},
    )


@router.get("/billing/plans", response_model=ApiResponse)
async def get_billing_plans(authorization: str | None = Header(default=None)) -> ApiResponse:
    await _resolve_session_user(authorization)
    from app.core.billing import list_billing_plans

    return ApiResponse(code=0, data={"plans": list_billing_plans()})


@router.post("/billing/orders", response_model=ApiResponse)
async def create_payment_order(
    payload: BillingOrderRequest,
    authorization: str | None = Header(default=None),
) -> ApiResponse:
    resolved = await _resolve_session_user(authorization)
    main_id = resolved["main_id"]
    current_user = resolved["user"]
    if resolve_space_type(current_user) != "personal":
        return ApiResponse(code=1, message="企业空间不能在用户端购买套餐，请联系企业管理员")
    from app.core.billing import create_billing_order, get_or_create_organization

    org = await get_or_create_organization(main_id)
    if str(org.get("owner_user_id")) != str(current_user["_id"]):
        return ApiResponse(code=1, message="只有组织创建者才能升级订阅套餐")
    if payload.paymentMethod == "dev_mock" and not get_settings().ENABLE_DEV_BILLING:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        order = await create_billing_order(
            main_id=main_id,
            buyer_user_id=str(current_user["_id"]),
            plan_code=payload.planCode,
            source="frontend",
            payment_method=payload.paymentMethod,
        )
    except ValueError as exc:
        return ApiResponse(code=1, message=str(exc))
    return ApiResponse(code=0, message="支付订单已创建", data={"order": order})


@router.get("/billing/orders/{order_no}", response_model=ApiResponse)
async def get_payment_order(
    order_no: str,
    authorization: str | None = Header(default=None),
) -> ApiResponse:
    resolved = await _resolve_session_user(authorization)
    from app.core.billing import get_billing_order

    order = await get_billing_order(resolved["main_id"], order_no)
    if not order:
        return ApiResponse(code=1, message="支付订单不存在")
    return ApiResponse(code=0, data={"order": order})


@router.post("/billing/orders/{order_no}/confirm-dev", response_model=ApiResponse)
async def confirm_payment_order_dev(
    order_no: str,
    authorization: str | None = Header(default=None),
) -> ApiResponse:
    if not get_settings().ENABLE_DEV_BILLING:
        raise HTTPException(status_code=404, detail="Not found")
    resolved = await _resolve_session_user(authorization)
    from app.core.billing import mark_order_paid_and_apply

    try:
        order = await mark_order_paid_and_apply(resolved["main_id"], order_no)
    except ValueError as exc:
        return ApiResponse(code=1, message=str(exc))
    return ApiResponse(code=0, message="支付已确认，套餐已生效", data={"order": order})


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
    
    data = {
        "mainId": org.get("main_id"),
        "orgName": org.get("org_name"),
        "tier": org.get("tier", "free"),
        "userLimit": org.get("user_limit", 5),
        "currentMembersCount": current_members,
        "totalPoints": org.get("total_points", 1000000),
        "usedPoints": org.get("used_points", 0),
        "remainingPoints": max(0, org.get("total_points", 1000000) - org.get("used_points", 0)),
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
