from __future__ import annotations

import base64
import hashlib
import hmac
import os
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId

from app.core.db import get_db
from app.core.config import get_settings
from app.llm.base import BaseLLMClient
from app.llm.capabilities import infer_structured_output_mode
from app.llm.instrumented_client import InstrumentedLLMClient
from app.llm.providers.azure_openai import AzureOpenAIClient
from app.llm.providers.default_openai import DefaultOpenAIClient

PROVIDER_COLLECTION = "admin_model_providers"
INSTANCE_COLLECTION = "admin_model_instances"
_configured_model_context: ContextVar[dict[str, Any] | None] = ContextVar("configured_model_context", default=None)


class ModelConfigError(ValueError):
    pass


def set_configured_model_context(config: dict[str, Any] | None) -> dict[str, Any] | None:
    previous = _configured_model_context.get()
    _configured_model_context.set(dict(config or {}) if config else None)
    return previous


def reset_configured_model_context(previous: dict[str, Any] | None) -> None:
    _configured_model_context.set(dict(previous or {}) if previous else None)


def get_configured_model_context() -> dict[str, Any] | None:
    current = _configured_model_context.get()
    return dict(current or {}) if current else None


def _validate_api_key_ascii(*, api_key: str, provider: str) -> None:
    key = str(api_key or "")
    if key and not key.isascii():
        raise ModelConfigError(
            f"Invalid {provider} API key: contains non-ASCII characters. "
            "Please check the model configuration in admin."
        )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _secret_key() -> bytes:
    secret = (
        os.getenv("MODEL_CONFIG_SECRET")
        or str(get_settings().ASKAI_ADMIN_JWT_SECRET or "")
        or os.getenv("ASKAI_ADMIN_JWT_SECRET")
        or "askai-admin-dev-secret"
    )
    return hashlib.sha256(secret.encode("utf-8")).digest()


def decrypt_secret(value: str) -> str:
    if not value:
        return ""
    packed = base64.urlsafe_b64decode(value.encode("ascii"))
    nonce, mac, cipher = packed[:16], packed[16:48], packed[48:]
    expected = hmac.new(_secret_key(), nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        raise ModelConfigError("模型 API Key 解密失败，请确认 backend 与 admin 使用相同的 ASKAI_ADMIN_JWT_SECRET")
    stream = _keystream(nonce, len(cipher))
    payload = bytes(left ^ right for left, right in zip(cipher, stream))
    return payload.decode("utf-8")


def _keystream(nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        counter_bytes = counter.to_bytes(4, "big")
        out.extend(hmac.new(_secret_key(), nonce + counter_bytes, hashlib.sha256).digest())
        counter += 1
    return bytes(out[:length])


async def get_model_config(model_id: str, main_id: str) -> dict[str, Any] | None:
    return await get_model_config_by_capability(model_id, main_id, capability=None)


async def get_model_config_by_capability(
    model_id: str,
    main_id: str,
    *,
    capability: str | None = "chat",
) -> dict[str, Any] | None:
    db = get_db()
    try:
        instance = await db[INSTANCE_COLLECTION].find_one({"_id": ObjectId(model_id), "main_id": main_id})
    except InvalidId as exc:
        raise ModelConfigError("模型配置 ID 无效") from exc
    if instance is None:
        return None
    provider = await db[PROVIDER_COLLECTION].find_one({"_id": instance.get("provider_id")})
    return _to_runtime_config(instance, provider or {}, required_capability=capability)


async def get_default_model_config(main_id: str) -> dict[str, Any] | None:
    return await get_default_model_config_by_capability(main_id, capability="chat")


async def get_default_model_config_by_capability(
    main_id: str,
    *,
    capability: str = "chat",
) -> dict[str, Any] | None:
    db = get_db()
    instance = await db[INSTANCE_COLLECTION].find_one(
        {
            "main_id": main_id,
            "status": "active",
            "capabilities": capability,
        },
        sort=[("priority", 1), ("updated_at", -1)],
    )
    if instance is None:
        return None
    provider = await db[PROVIDER_COLLECTION].find_one({"_id": instance.get("provider_id")})
    return _to_runtime_config(instance, provider or {}, required_capability=capability)


async def list_chat_model_options(main_id: str) -> list[dict[str, Any]]:
    return await list_model_options(main_id, capability="chat")


async def list_model_options(
    main_id: str,
    *,
    capability: str = "chat",
) -> list[dict[str, Any]]:
    db = get_db()
    cursor = db[INSTANCE_COLLECTION].find(
        {
            "main_id": main_id,
            "status": "active",
            "capabilities": capability,
        }
    ).sort([("priority", 1), ("updated_at", -1)])
    instances = await cursor.to_list(length=200)
    provider_ids = [item.get("provider_id") for item in instances if item.get("provider_id")]
    provider_map: dict[str, dict[str, Any]] = {}
    if provider_ids:
        async for provider in db[PROVIDER_COLLECTION].find({"_id": {"$in": provider_ids}}):
            provider_map[str(provider.get("_id"))] = provider
    return [_to_public_option(item, provider_map.get(str(item.get("provider_id")), {})) for item in instances]


async def update_model_health(model_id: str, main_id: str, health_status: str, last_error: str = "") -> None:
    db = get_db()
    await db[INSTANCE_COLLECTION].update_one(
        {"_id": ObjectId(model_id), "main_id": main_id},
        {
            "$set": {
                "health_status": health_status,
                "last_error": str(last_error or "")[:1000],
                "last_checked_at": _utcnow(),
                "updated_at": _utcnow(),
            }
        },
    )


def _to_public_option(instance: dict[str, Any], provider: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(instance.get("_id") or ""),
        "displayName": instance.get("display_name") or instance.get("model_name") or "",
        "modelName": instance.get("model_name") or "",
        "providerName": provider.get("name") or "",
        "providerType": provider.get("provider_type") or "openai_compatible",
        "runtimeKind": str(instance.get("runtime_kind") or provider.get("runtime_kind") or "").strip(),
        "capabilities": _normalize_capabilities(instance.get("capabilities")),
        "isDefault": bool(instance.get("is_default")),
        "healthStatus": instance.get("health_status") or "unknown",
    }


def _to_runtime_config(
    instance: dict[str, Any],
    provider: dict[str, Any],
    *,
    required_capability: str | None = "chat",
) -> dict[str, Any]:
    provider_type = str(provider.get("provider_type") or "openai_compatible").strip()
    api_key = decrypt_secret(str(instance.get("api_key_encrypted") or ""))
    settings = instance.get("settings")
    if not isinstance(settings, dict):
        settings = provider.get("settings") if isinstance(provider.get("settings"), dict) else {}
    config = {
        "id": str(instance.get("_id") or ""),
        "main_id": str(instance.get("main_id") or ""),
        "display_name": str(instance.get("display_name") or ""),
        "provider_type": provider_type,
        "provider_name": str(provider.get("name") or ""),
        "model_name": str(instance.get("model_name") or "").strip(),
        "base_url": str(instance.get("base_url") or provider.get("default_base_url") or "").strip(),
        "api_version": str(instance.get("api_version") or "").strip(),
        "api_key": api_key,
        "status": str(instance.get("status") or ""),
        "capabilities": _normalize_capabilities(instance.get("capabilities")),
        "is_default": bool(instance.get("is_default")),
        "runtime_kind": str(instance.get("runtime_kind") or provider.get("runtime_kind") or "").strip(),
        "settings": dict(settings or {}),
    }
    config["structured_output_mode"] = infer_structured_output_mode(
        provider_type=provider_type,
        provider_name=str(provider.get("name") or ""),
        model_name=str(config.get("model_name") or ""),
        settings=config.get("settings") if isinstance(config.get("settings"), dict) else None,
        api_version=str(config.get("api_version") or ""),
    )
    _validate_runtime_config(config, required_capability=required_capability)
    return config


def _normalize_capabilities(raw: Any) -> list[str]:
    if isinstance(raw, str):
        return [raw] if raw else []
    if isinstance(raw, (list, tuple, set)):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def _validate_runtime_config(
    config: dict[str, Any],
    *,
    required_capability: str | None = "chat",
) -> None:
    if config.get("status") != "active":
        raise ModelConfigError("模型配置已禁用")
    capability = str(required_capability or "").strip()
    if capability and capability not in list(config.get("capabilities") or []):
        raise ModelConfigError(f"模型配置不支持能力: {capability}")
    if not str(config.get("model_name") or "").strip():
        raise ModelConfigError("模型 ID 不能为空")
    if not str(config.get("base_url") or "").strip():
        raise ModelConfigError("Base URL 不能为空")
    if not str(config.get("api_key") or "").strip():
        raise ModelConfigError("API Key 不能为空")


def build_llm_client_from_config(
    config: dict[str, Any],
    *,
    streaming: bool = True,
    intent: str | None = None,
    stage: str | None = None,
    node_id: str | None = None,
    output_spec: dict[str, Any] | None = None,
) -> BaseLLMClient:
    provider_type = str(config.get("provider_type") or "openai_compatible")
    api_key = str(config.get("api_key") or "")
    model_name = str(config.get("model_name") or "")
    _validate_api_key_ascii(api_key=api_key, provider=str(config.get("provider_name") or provider_type))
    if provider_type == "azure_openai":
        client: BaseLLMClient = AzureOpenAIClient(
            api_key=api_key,
            azure_endpoint=str(config.get("base_url") or ""),
            api_version=str(config.get("api_version") or "") or "2024-10-21",
            azure_deployment=model_name,
            streaming=streaming,
        )
    else:
        client = DefaultOpenAIClient(
            api_key=api_key,
            base_url=str(config.get("base_url") or "").rstrip("/"),
            model=model_name,
            streaming=streaming,
            structured_output_mode=str(config.get("structured_output_mode") or "prompt_json"),
        )
    safe_output_spec = dict(output_spec or {})
    safe_output_spec.pop("configured_model", None)
    return InstrumentedLLMClient(
        client,
        model_name=model_name,
        model_id=str(config.get("id") or model_name),
        stage=stage,
        intent=intent,
        node_id=node_id,
        output_spec=safe_output_spec,
    )


async def get_llm_client_by_model_id(
    model_id: str | None,
    *,
    main_id: str,
    streaming: bool = True,
    intent: str | None = None,
    stage: str | None = None,
    node_id: str | None = None,
    output_spec: dict[str, Any] | None = None,
) -> BaseLLMClient:
    config = await get_model_config(model_id, main_id) if model_id else await get_default_model_config(main_id)
    if config is None:
        raise ModelConfigError("没有可用的模型配置")
    
    user_id = str((output_spec or {}).get("user_id") or "").strip()
    if user_id and ObjectId.is_valid(user_id):
        user_doc = await get_db()["end_users"].find_one({"_id": ObjectId(user_id), "main_id": main_id})
        if user_doc:
            from app.core.quota_policy import QuotaExceededError, assert_quota_available

            try:
                await assert_quota_available(main_id, user_doc)
            except QuotaExceededError as exc:
                raise ModelConfigError(str(exc)) from exc

    return build_llm_client_from_config(
        config,
        streaming=streaming,
        intent=intent,
        stage=stage,
        node_id=node_id,
        output_spec=output_spec,
    )
