from __future__ import annotations

import datetime
import uuid
from typing import Any

from app.core.db import get_db
from app.repositories.model_repository import encrypt_secret, mask_secret
from app.services.external_search_provider import PROVIDERS, normalized_config, test_provider


COLLECTION = "external_search_configs"


def setup_provider_catalog() -> list[dict[str, str]]:
    return [
        {
            "id": provider,
            "name": str(meta["label"]),
            "description": str(meta["description"]),
            "defaultEndpoint": str(meta["endpoint"]),
            "defaultBaseUrl": str(meta["base_url"]),
        }
        for provider, meta in PROVIDERS.items()
    ]


async def test_setup_search(payload: dict[str, Any]) -> list[dict[str, str]]:
    provider = str(payload.get("provider") or "").strip()
    config = normalized_config(
        provider,
        api_key=str(payload.get("apiKey") or ""),
        endpoint=str(payload.get("endpoint") or ""),
        base_url=str(payload.get("baseUrl") or ""),
        model=str(payload.get("model") or ""),
    )
    return await test_provider(provider, config, str(payload.get("query") or ""))


async def save_setup_search(payload: dict[str, Any], main_id: str) -> None:
    provider = str(payload.get("provider") or "").strip()
    config = normalized_config(
        provider,
        api_key=str(payload.get("apiKey") or ""),
        endpoint=str(payload.get("endpoint") or ""),
        base_url=str(payload.get("baseUrl") or ""),
        model=str(payload.get("model") or ""),
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    await get_db()[COLLECTION].update_one(
        {"main_id": main_id, "provider": provider},
        {
            "$set": {
                "enabled": True,
                "is_default": True,
                "priority": int(PROVIDERS[provider]["priority"]),
                "config": {
                    "api_key_encrypted": encrypt_secret(config["api_key"]),
                    "api_key_masked": mask_secret(config["api_key"]),
                    "endpoint": config["endpoint"],
                    "base_url": config["base_url"],
                    "model": config["model"],
                },
                "health_status": "healthy",
                "last_error": "",
                "last_test_at": now,
                "updated_by": "setup",
                "updated_at": now,
            },
            "$setOnInsert": {
                "_id": uuid.uuid4().hex,
                "main_id": main_id,
                "provider": provider,
                "created_at": now,
            },
        },
        upsert=True,
    )
