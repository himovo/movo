from __future__ import annotations

import datetime
import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_current_admin_user
from app.api.time_utils import utc_iso
from app.core.db import get_db
from app.repositories.model_repository import encrypt_secret, mask_secret

router = APIRouter()

COLLECTION = "page_collection_settings"
PROVIDER = "firecrawl"


class PageCollectionPayload(BaseModel):
    enabled: bool = True
    apiKey: str = Field(default="", max_length=1000)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _main_id(current_user: dict[str, Any]) -> str:
    return str(current_user.get("main_id") or "default")


def _time_text(value: Any) -> str:
    return utc_iso(value)


def _config(doc: dict[str, Any] | None) -> dict[str, Any]:
    raw = (doc or {}).get("config")
    return dict(raw or {}) if isinstance(raw, dict) else {}


def _serialize(doc: dict[str, Any] | None) -> dict[str, Any]:
    config = _config(doc)
    return {
        "id": str((doc or {}).get("_id") or ""),
        "provider": PROVIDER,
        "label": "Firecrawl",
        "enabled": bool((doc or {}).get("enabled", False)),
        "apiKeyMasked": str(config.get("api_key_masked") or ""),
        "updatedAt": _time_text((doc or {}).get("updated_at")),
    }


async def _load_doc(main_id: str) -> dict[str, Any] | None:
    return await get_db()[COLLECTION].find_one({"main_id": main_id, "provider": PROVIDER})


@router.get("")
async def get_page_collection_settings(current_user: dict[str, Any] = Depends(get_current_admin_user)) -> dict[str, Any]:
    return _serialize(await _load_doc(_main_id(current_user)))


@router.put("")
async def save_page_collection_settings(
    payload: PageCollectionPayload,
    current_user: dict[str, Any] = Depends(get_current_admin_user),
) -> dict[str, Any]:
    main_id = _main_id(current_user)
    existing = await _load_doc(main_id)
    existing_config = _config(existing)
    config: dict[str, Any] = {}
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
        {"main_id": main_id, "provider": PROVIDER},
        {
            "$set": {
                "enabled": bool(payload.enabled),
                "config": config,
                "updated_by": str(current_user.get("username") or ""),
                "updated_at": now,
            },
            "$setOnInsert": {
                "_id": doc_id,
                "main_id": main_id,
                "provider": PROVIDER,
                "created_at": now,
            },
        },
        upsert=True,
    )
    return _serialize(await _load_doc(main_id))


async def ensure_indexes() -> None:
    db = get_db()
    await db[COLLECTION].create_index([("main_id", 1), ("provider", 1)], unique=True)
    await db[COLLECTION].create_index([("main_id", 1), ("enabled", 1)])
