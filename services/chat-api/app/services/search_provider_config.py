from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.core.db import get_db
from app.llm.configured_models import decrypt_secret


COLLECTION = "external_search_configs"
SUPPORTED_PROVIDERS = {"tavily", "serper", "serpapi", "baidu_qianfan", "volc_ark"}


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
        doc = await db[COLLECTION].find_one(
            {
                "main_id": candidate_main_id,
                "enabled": True,
                "is_default": True,
                "provider": {"$in": sorted(SUPPORTED_PROVIDERS)},
            },
            sort=[("priority", 1), ("updated_at", -1)],
        )
        if doc:
            return _safe_config(doc)
    return None


def env_external_search_config(provider: str) -> dict[str, Any] | None:
    settings = get_settings()
    token = str(provider or "").strip()
    if token == "tavily":
        api_key = str(getattr(settings, "TAVILY_API_KEY", "") or "").strip()
        if not api_key:
            return None
        return {"provider": token, "source": "env_fallback", "api_key": api_key}
    return None
