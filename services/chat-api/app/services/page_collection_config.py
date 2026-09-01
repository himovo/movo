from __future__ import annotations

from typing import Any

from app.core.db import get_db
from app.llm.configured_models import decrypt_secret


COLLECTION = "page_collection_settings"


async def resolve_firecrawl_api_key(main_id: str) -> str:
    resolved_main_id = str(main_id or "default").strip() or "default"
    db = get_db()
    for candidate_main_id in ([resolved_main_id, "default"] if resolved_main_id != "default" else ["default"]):
        doc = await db[COLLECTION].find_one({"main_id": candidate_main_id, "provider": "firecrawl", "enabled": True})
        if not doc:
            continue
        config = doc.get("config") if isinstance(doc.get("config"), dict) else {}
        encrypted = str((config or {}).get("api_key_encrypted") or "")
        return decrypt_secret(encrypted) if encrypted else ""
    return ""


def serialize_firecrawl_config(doc: dict[str, Any] | None) -> dict[str, Any]:
    config = doc.get("config") if isinstance((doc or {}).get("config"), dict) else {}
    return {
        "provider": "firecrawl",
        "label": "Firecrawl",
        "enabled": bool((doc or {}).get("enabled", False)),
        "apiKeyMasked": str((config or {}).get("api_key_masked") or ""),
        "updatedAt": (doc or {}).get("updated_at"),
    }
