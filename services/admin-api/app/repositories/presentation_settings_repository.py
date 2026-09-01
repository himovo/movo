from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.db import get_db


COLLECTION = "admin_presentation_settings"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def get_presentation_settings(main_id: str) -> dict[str, Any] | None:
    return await get_db()[COLLECTION].find_one({"main_id": main_id})


async def save_presentation_settings(
    *,
    main_id: str,
    generation_mode: str,
    llm_model_id: str,
    image_model_id: str,
    vision_model_id: str,
    updated_by: str,
) -> dict[str, Any]:
    now = utcnow()
    await get_db()[COLLECTION].update_one(
        {"main_id": main_id},
        {
            "$set": {
                "generation_mode": generation_mode,
                "llm_model_id": llm_model_id,
                "image_model_id": image_model_id,
                "vision_model_id": vision_model_id,
                "updated_by": updated_by,
                "updated_at": now,
            },
            "$setOnInsert": {"main_id": main_id, "created_at": now},
        },
        upsert=True,
    )
    saved = await get_presentation_settings(main_id)
    if saved is None:
        raise RuntimeError("PPT 生成设置保存失败")
    return saved


__all__ = [
    "COLLECTION",
    "get_presentation_settings",
    "save_presentation_settings",
]
