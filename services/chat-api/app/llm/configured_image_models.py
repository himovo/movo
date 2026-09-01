from __future__ import annotations

from typing import Any

from app.llm.configured_models import (
    ModelConfigError,
    get_default_model_config_by_capability,
    get_model_config_by_capability,
    list_model_options,
    update_model_health,
)


IMAGE_CAPABILITY = "image_generation"


async def get_image_model_config(model_id: str, main_id: str) -> dict[str, Any] | None:
    return await get_model_config_by_capability(model_id, main_id, capability=IMAGE_CAPABILITY)


async def get_default_image_model_config(main_id: str) -> dict[str, Any] | None:
    return await get_default_model_config_by_capability(main_id, capability=IMAGE_CAPABILITY)


async def list_image_model_options(main_id: str) -> list[dict[str, Any]]:
    return await list_model_options(main_id, capability=IMAGE_CAPABILITY)


__all__ = [
    "IMAGE_CAPABILITY",
    "ModelConfigError",
    "get_default_image_model_config",
    "get_image_model_config",
    "list_image_model_options",
    "update_model_health",
]
