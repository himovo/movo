from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.core.db import get_db
from app.llm.configured_models import decrypt_secret


COLLECTION = "external_search_configs"
PROVIDER_PRIORITIES = {
    "deepseek": 5,
    "tavily": 10,
    "serper": 20,
    "serpapi": 30,
    "baidu_qianfan": 40,
    "volc_ark": 50,
    "specstream": 60,
}
SUPPORTED_PROVIDERS = set(PROVIDER_PRIORITIES)


def _safe_config(doc: dict[str, Any]) -> dict[str, Any]:
    raw = doc.get("config")
    if not isinstance(raw, dict):
        raw = {}
    api_key = decrypt_secret(str(raw.get("api_key_encrypted") or "")) if raw.get("api_key_encrypted") else ""
    return {
        "provider": str(doc.get("provider") or "").strip(),
        "source": "admin_config",
        "api_key": api_key,
        "endpoint": str(raw.get("endpoint") or "").strip(),
        "base_url": str(raw.get("base_url") or "").strip(),
        "model": str(raw.get("model") or "").strip(),
    }


async def resolve_default_external_search_provider(main_id: str) -> dict[str, Any] | None:
    resolved_main_id = str(main_id or "default").strip() or "default"
    db = get_db()
    for candidate_main_id in ([resolved_main_id, "default"] if resolved_main_id != "default" else ["default"]):
        enabled_docs = await db[COLLECTION].find(
            {"main_id": candidate_main_id, "enabled": True, "provider": {"$in": sorted(SUPPORTED_PROVIDERS)}},
        ).to_list(length=len(SUPPORTED_PROVIDERS))
        usable = [
            doc for doc in enabled_docs
            if isinstance(doc.get("config"), dict) and doc["config"].get("api_key_encrypted")
        ]
        if usable:
            selected = min(
                usable,
                key=lambda doc: (
                    not bool(doc.get("is_default")),
                    int(doc.get("priority") or PROVIDER_PRIORITIES[str(doc["provider"])]),
                    str(doc.get("provider") or ""),
                ),
            )
            return _safe_config(selected)
        if candidate_main_id == resolved_main_id and resolved_main_id != "default":
            # An organization's disabled selection must not inherit another
            # organization's default source (or its paid API credentials).
            if await has_saved_external_search_config(resolved_main_id):
                return None
    return None


async def has_saved_external_search_config(main_id: str) -> bool:
    """Once an organization manages search in Admin, never silently use host keys."""
    resolved_main_id = str(main_id or "default").strip() or "default"
    db = get_db()
    return bool(await db[COLLECTION].find_one({"main_id": resolved_main_id}, {"_id": 1}))


def env_external_search_config(provider: str) -> dict[str, Any] | None:
    settings = get_settings()
    token = str(provider or "").strip()
    if token == "tavily":
        api_key = str(getattr(settings, "TAVILY_API_KEY", "") or "").strip()
        if not api_key:
            return None
        return {"provider": token, "source": "env_fallback", "api_key": api_key}
    return None
