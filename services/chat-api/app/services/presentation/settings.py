from __future__ import annotations

from typing import Any

from app.core.db import get_db


COLLECTION = "admin_presentation_settings"


async def get_presentation_generation_settings(main_id: str) -> dict[str, Any] | None:
    doc = await get_db()[COLLECTION].find_one({"main_id": main_id})
    if not doc:
        return None
    return {
        "generation_mode": str(doc.get("generation_mode") or "llm").strip(),
        "llm_model_id": str(doc.get("llm_model_id") or "").strip(),
        "image_model_id": str(doc.get("image_model_id") or "").strip(),
        "vision_model_id": str(doc.get("vision_model_id") or "").strip(),
    }


__all__ = ["get_presentation_generation_settings"]
