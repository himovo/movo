from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pymongo.errors import OperationFailure

from app.core.config import settings
from app.core.db import get_db

PROVIDER_COLLECTION = "admin_model_providers"
INSTANCE_COLLECTION = "admin_model_instances"

DEFAULT_PROVIDERS = [
    {
        "name": "OpenAI",
        "code": "openai",
        "provider_type": "openai_compatible",
        "default_base_url": "https://api.openai.com/v1",
        "auth_type": "bearer",
        "status": "active",
        "priority": 10,
    },
    {
        "name": "Azure OpenAI",
        "code": "azure-openai",
        "provider_type": "azure_openai",
        "default_base_url": "https://YOUR-RESOURCE-NAME.openai.azure.com",
        "auth_type": "api_key",
        "status": "active",
        "priority": 15,
    },
    {
        "name": "通义千问",
        "code": "qwen",
        "provider_type": "openai_compatible",
        "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "auth_type": "bearer",
        "status": "active",
        "priority": 20,
    },
    {
        "name": "DeepSeek",
        "code": "deepseek",
        "provider_type": "openai_compatible",
        "default_base_url": "https://api.deepseek.com",
        "auth_type": "bearer",
        "status": "active",
        "priority": 30,
    },
    {
        "name": "自定义兼容接口",
        "code": "custom-openai-compatible",
        "provider_type": "openai_compatible",
        "default_base_url": "",
        "auth_type": "bearer",
        "status": "active",
        "priority": 90,
    },
]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def ensure_indexes() -> None:
    db = get_db()
    try:
        await db[PROVIDER_COLLECTION].create_index("code", unique=True, name="provider_code_unique")
        await db[PROVIDER_COLLECTION].create_index("status", name="provider_status")
        await db[INSTANCE_COLLECTION].create_index(
            [("main_id", 1), ("provider_id", 1), ("model_name", 1), ("display_name", 1)],
            unique=True,
            name="model_instance_identity_unique",
        )
        await db[INSTANCE_COLLECTION].create_index([("main_id", 1), ("status", 1)], name="model_main_status")
        await db[INSTANCE_COLLECTION].create_index([("main_id", 1), ("is_default", 1)], name="model_main_default")
    except OperationFailure:
        pass
    await seed_default_providers()


async def seed_default_providers() -> None:
    db = get_db()
    now = utcnow()
    for provider in DEFAULT_PROVIDERS:
        await db[PROVIDER_COLLECTION].update_one(
            {"code": provider["code"]},
            {
                "$setOnInsert": {
                    "code": provider["code"],
                    "created_at": now,
                },
                "$set": {
                    "name": provider["name"],
                    "provider_type": provider["provider_type"],
                    "default_base_url": provider["default_base_url"],
                    "auth_type": provider["auth_type"],
                    "status": provider["status"],
                    "priority": provider["priority"],
                    "updated_at": now,
                },
            },
            upsert=True,
        )


async def list_providers() -> list[dict[str, Any]]:
    db = get_db()
    cursor = db[PROVIDER_COLLECTION].find({}).sort([("priority", 1), ("name", 1)])
    return await cursor.to_list(length=100)


async def find_provider_by_id(provider_id: str) -> dict[str, Any] | None:
    db = get_db()
    return await db[PROVIDER_COLLECTION].find_one({"_id": ObjectId(provider_id)})


async def list_instances(main_id: str) -> list[dict[str, Any]]:
    db = get_db()
    cursor = db[INSTANCE_COLLECTION].find({"main_id": main_id}).sort([("priority", 1), ("updated_at", -1)])
    return await cursor.to_list(length=500)


async def find_instance_by_id(instance_id: str, main_id: str) -> dict[str, Any] | None:
    db = get_db()
    return await db[INSTANCE_COLLECTION].find_one({"_id": ObjectId(instance_id), "main_id": main_id})


async def create_instance(payload: dict[str, Any]) -> str:
    db = get_db()
    now = utcnow()
    doc = {
        "main_id": payload["main_id"],
        "provider_id": ObjectId(payload["provider_id"]),
        "org_id": payload.get("org_id") or "",
        "display_name": payload["display_name"],
        "model_name": payload["model_name"],
        "base_url": payload.get("base_url") or "",
        "api_key_encrypted": encrypt_secret(payload.get("api_key") or ""),
        "api_key_masked": mask_secret(payload.get("api_key") or ""),
        "api_secret_encrypted": encrypt_secret(payload.get("api_secret") or ""),
        "api_secret_masked": mask_secret(payload.get("api_secret") or ""),
        "api_version": str(payload.get("api_version") or "").strip(),
        "capabilities": payload.get("capabilities") or ["chat"],
        "max_context_tokens": int(payload.get("max_context_tokens") or 0),
        "status": payload.get("status") or "active",
        "health_status": "unknown",
        "last_error": "",
        "is_default": bool(payload.get("is_default", False)),
        "priority": int(payload.get("priority") or 100),
        "created_at": now,
        "updated_at": now,
    }
    result = await db[INSTANCE_COLLECTION].insert_one(doc)
    if doc["is_default"]:
        await set_default_instance(str(result.inserted_id), payload["main_id"])
    return str(result.inserted_id)


async def update_instance(instance_id: str, payload: dict[str, Any]) -> bool:
    db = get_db()
    set_doc: dict[str, Any] = {
        "provider_id": ObjectId(payload["provider_id"]),
        "org_id": payload.get("org_id") or "",
        "display_name": payload["display_name"],
        "model_name": payload["model_name"],
        "base_url": payload.get("base_url") or "",
        "api_version": str(payload.get("api_version") or "").strip(),
        "capabilities": payload.get("capabilities") or ["chat"],
        "max_context_tokens": int(payload.get("max_context_tokens") or 0),
        "status": payload.get("status") or "active",
        "is_default": bool(payload.get("is_default", False)),
        "priority": int(payload.get("priority") or 100),
        "updated_at": utcnow(),
    }
    if payload.get("api_key"):
        set_doc["api_key_encrypted"] = encrypt_secret(payload["api_key"])
        set_doc["api_key_masked"] = mask_secret(payload["api_key"])
    if payload.get("api_secret"):
        set_doc["api_secret_encrypted"] = encrypt_secret(payload["api_secret"])
        set_doc["api_secret_masked"] = mask_secret(payload["api_secret"])

    result = await db[INSTANCE_COLLECTION].update_one(
        {"_id": ObjectId(instance_id), "main_id": payload["main_id"]},
        {"$set": set_doc},
    )
    if result.matched_count > 0 and set_doc["is_default"]:
        await set_default_instance(instance_id, payload["main_id"])
    return result.matched_count > 0


async def delete_instance(instance_id: str, main_id: str) -> bool:
    db = get_db()
    result = await db[INSTANCE_COLLECTION].delete_one({"_id": ObjectId(instance_id), "main_id": main_id})
    return result.deleted_count > 0


async def set_default_instance(instance_id: str, main_id: str) -> bool:
    db = get_db()
    instance = await find_instance_by_id(instance_id, main_id)
    if instance is None:
        return False
    now = utcnow()
    await db[INSTANCE_COLLECTION].update_many(
        {"main_id": main_id, "_id": {"$ne": ObjectId(instance_id)}},
        {"$set": {"is_default": False, "updated_at": now}},
    )
    await db[INSTANCE_COLLECTION].update_one(
        {"_id": ObjectId(instance_id), "main_id": main_id},
        {"$set": {"is_default": True, "updated_at": now}},
    )
    return True


async def update_instance_health(instance_id: str, main_id: str, health_status: str, last_error: str = "") -> None:
    db = get_db()
    await db[INSTANCE_COLLECTION].update_one(
        {"_id": ObjectId(instance_id), "main_id": main_id},
        {
            "$set": {
                "health_status": health_status,
                "last_error": str(last_error or "")[:1000],
                "last_checked_at": utcnow(),
                "updated_at": utcnow(),
            }
        },
    )


def mask_secret(value: str) -> str:
    secret = str(value or "").strip()
    if not secret:
        return ""
    if len(secret) <= 8:
        return f"{secret[:2]}****"
    return f"{secret[:4]}****{secret[-4:]}"


def encrypt_secret(value: str) -> str:
    secret = str(value or "")
    if not secret:
        return ""
    nonce = secrets.token_bytes(16)
    payload = secret.encode("utf-8")
    stream = _keystream(nonce, len(payload))
    cipher = bytes(left ^ right for left, right in zip(payload, stream))
    mac = hmac.new(_secret_key(), nonce + cipher, hashlib.sha256).digest()
    packed = nonce + mac + cipher
    return base64.urlsafe_b64encode(packed).decode("ascii")


def decrypt_secret(value: str) -> str:
    if not value:
        return ""
    packed = base64.urlsafe_b64decode(value.encode("ascii"))
    nonce, mac, cipher = packed[:16], packed[16:48], packed[48:]
    expected = hmac.new(_secret_key(), nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        raise ValueError("Invalid encrypted secret")
    stream = _keystream(nonce, len(cipher))
    payload = bytes(left ^ right for left, right in zip(cipher, stream))
    return payload.decode("utf-8")


def _secret_key() -> bytes:
    return hashlib.sha256(settings.jwt_secret.encode("utf-8")).digest()


def _keystream(nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        counter_bytes = counter.to_bytes(4, "big")
        out.extend(hmac.new(_secret_key(), nonce + counter_bytes, hashlib.sha256).digest())
        counter += 1
    return bytes(out[:length])
