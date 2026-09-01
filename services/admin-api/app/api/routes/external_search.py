from __future__ import annotations

import datetime
import urllib.error
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import get_current_admin_user
from app.api.time_utils import utc_iso
from app.core.db import get_db
from app.repositories.model_repository import decrypt_secret, encrypt_secret, mask_secret
from app.services.external_search_provider import (
    PROVIDERS,
    ExternalSearchConfigError,
    normalized_config,
    provider_or_error,
    test_provider,
)

router = APIRouter()

COLLECTION = "external_search_configs"
class SearchProviderPayload(BaseModel):
    enabled: bool = True
    apiKey: str = Field(default="", max_length=1000)
    endpoint: str = Field(default="", max_length=500)
    baseUrl: str = Field(default="", max_length=500)
    model: str = Field(default="", max_length=200)


class SearchProviderTestPayload(BaseModel):
    query: str = Field(default="OpenAI latest news", max_length=300)
    apiKey: str = Field(default="", max_length=1000)
    endpoint: str = Field(default="", max_length=500)
    baseUrl: str = Field(default="", max_length=500)
    model: str = Field(default="", max_length=200)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _main_id(current_user: dict[str, Any]) -> str:
    return str(current_user.get("main_id") or "default")


def _time_text(value: Any) -> str:
    return utc_iso(value)


def _provider_or_404(provider: str) -> str:
    try:
        return provider_or_error(provider)
    except ExternalSearchConfigError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="搜索源不存在")



def _config(doc: dict[str, Any] | None) -> dict[str, Any]:
    raw = (doc or {}).get("config")
    return dict(raw or {}) if isinstance(raw, dict) else {}


def _api_key_from_config(config: dict[str, Any]) -> str:
    encrypted = str(config.get("api_key_encrypted") or "")
    return decrypt_secret(encrypted) if encrypted else ""


def _effective_default_provider(docs: list[dict[str, Any]]) -> str:
    doc_map = {str(doc.get("provider") or ""): doc for doc in docs if doc.get("is_default") and doc.get("enabled")}
    for provider in PROVIDERS:
        if provider in doc_map:
            return provider
    return ""


def _serialize(provider: str, doc: dict[str, Any] | None, *, default_provider: str | None = None) -> dict[str, Any]:
    meta = PROVIDERS[provider]
    config = _config(doc)
    return {
        "id": str((doc or {}).get("_id") or ""),
        "provider": provider,
        "label": meta["label"],
        "enabled": bool((doc or {}).get("enabled", False)),
        "isDefault": bool((provider == default_provider) if default_provider is not None else (doc or {}).get("is_default", False)),
        "priority": int((doc or {}).get("priority") or meta["priority"]),
        "endpoint": str(config.get("endpoint") or meta["endpoint"]),
        "baseUrl": str(config.get("base_url") or meta["base_url"]),
        "model": str(config.get("model") or meta["model"]),
        "apiKeyMasked": str(config.get("api_key_masked") or ""),
        "healthStatus": str((doc or {}).get("health_status") or "untested"),
        "lastError": str((doc or {}).get("last_error") or ""),
        "updatedAt": _time_text((doc or {}).get("updated_at")),
    }


async def _load_provider_doc(main_id: str, provider: str) -> dict[str, Any] | None:
    return await get_db()[COLLECTION].find_one({"main_id": main_id, "provider": provider})


@router.get("/providers")
async def list_external_search_providers(current_user: dict[str, Any] = Depends(get_current_admin_user)) -> list[dict[str, Any]]:
    main_id = _main_id(current_user)
    docs = await get_db()[COLLECTION].find({"main_id": main_id}).to_list(length=20)
    doc_map = {str(doc.get("provider") or ""): doc for doc in docs}
    default_provider = _effective_default_provider(docs)
    return [_serialize(provider, doc_map.get(provider), default_provider=default_provider) for provider in PROVIDERS]


@router.put("/providers/{provider}")
async def save_external_search_provider(
    provider: str,
    payload: SearchProviderPayload,
    current_user: dict[str, Any] = Depends(get_current_admin_user),
) -> dict[str, Any]:
    provider = _provider_or_404(provider)
    main_id = _main_id(current_user)
    existing = await _load_provider_doc(main_id, provider)
    existing_config = _config(existing)
    config = {
        "endpoint": payload.endpoint.strip() or PROVIDERS[provider]["endpoint"],
        "base_url": payload.baseUrl.strip() or PROVIDERS[provider]["base_url"],
        "model": payload.model.strip() or PROVIDERS[provider]["model"],
    }
    if payload.apiKey.strip():
        config["api_key_encrypted"] = encrypt_secret(payload.apiKey)
        config["api_key_masked"] = mask_secret(payload.apiKey)
    else:
        for key in ("api_key_encrypted", "api_key_masked"):
            if key in existing_config:
                config[key] = existing_config[key]
    now = _now()
    doc_id = str((existing or {}).get("_id") or uuid.uuid4().hex)
    await get_db()[COLLECTION].update_one(
        {"main_id": main_id, "provider": provider},
        {
            "$set": {
                "enabled": bool(payload.enabled),
                "config": config,
                "priority": int(PROVIDERS[provider]["priority"]),
                **({"is_default": False} if not payload.enabled else {}),
                "updated_by": str(current_user.get("username") or ""),
                "updated_at": now,
            },
            "$setOnInsert": {
                "_id": doc_id,
                "main_id": main_id,
                "provider": provider,
                "is_default": False,
                "health_status": "untested",
                "last_error": "",
                "created_at": now,
            },
        },
        upsert=True,
    )
    doc = await _load_provider_doc(main_id, provider)
    return _serialize(provider, doc)


@router.post("/providers/{provider}/default")
async def set_default_external_search_provider(
    provider: str,
    current_user: dict[str, Any] = Depends(get_current_admin_user),
) -> dict[str, bool]:
    provider = _provider_or_404(provider)
    main_id = _main_id(current_user)
    doc = await _load_provider_doc(main_id, provider)
    if not doc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先保存搜索源配置")
    await get_db()[COLLECTION].update_many({"main_id": main_id}, {"$set": {"is_default": False, "updated_at": _now()}})
    await get_db()[COLLECTION].update_one(
        {"main_id": main_id, "provider": provider},
        {"$set": {"is_default": True, "enabled": True, "updated_at": _now()}},
    )
    return {"success": True}


@router.post("/providers/{provider}/test")
async def test_external_search_provider(
    provider: str,
    payload: SearchProviderTestPayload,
    current_user: dict[str, Any] = Depends(get_current_admin_user),
) -> dict[str, Any]:
    provider = _provider_or_404(provider)
    main_id = _main_id(current_user)
    doc = await _load_provider_doc(main_id, provider)
    config = _config(doc)
    api_key = payload.apiKey.strip() or _api_key_from_config(config)
    query = payload.query.strip() or "OpenAI latest news"
    try:
        effective = normalized_config(
            provider,
            api_key=api_key,
            endpoint=payload.endpoint.strip() or str(config.get("endpoint") or ""),
            base_url=payload.baseUrl.strip() or str(config.get("base_url") or ""),
            model=payload.model.strip() or str(config.get("model") or ""),
        )
        results = await test_provider(provider, effective, query)
        status_text = "healthy" if results else "failed"
        error = "" if results else "未返回搜索结果"
    except ExternalSearchConfigError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except urllib.error.HTTPError as exc:
        results = []
        status_text = "failed"
        error = exc.read().decode("utf-8", errors="replace")[:1000] or str(exc)
    except Exception as exc:
        results = []
        status_text = "failed"
        error = str(exc)[:1000]
    if doc:
        await get_db()[COLLECTION].update_one(
            {"main_id": main_id, "provider": provider},
            {"$set": {"health_status": status_text, "last_error": error, "last_test_at": _now(), "updated_at": _now()}},
        )
    return {
        "ok": status_text == "healthy",
        "provider": provider,
        "resultCount": len(results),
        "sampleResults": results,
        "message": "连接成功" if status_text == "healthy" else error,
    }


async def ensure_indexes() -> None:
    db = get_db()
    await db[COLLECTION].create_index([("main_id", 1), ("provider", 1)], unique=True)
    await db[COLLECTION].create_index([("main_id", 1), ("enabled", 1), ("is_default", 1)])
