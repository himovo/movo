from __future__ import annotations

from typing import Any

from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import get_current_admin_user
from app.api.time_utils import utc_iso
from app.repositories.model_repository import find_instance_by_id
from app.repositories.presentation_settings_repository import (
    get_presentation_settings,
    save_presentation_settings,
)
from app.services.image_model_configuration import normalize_capabilities


router = APIRouter()


class PresentationSettingsPayload(BaseModel):
    enabled: bool = False
    llmModelId: str = Field(default="", max_length=120)
    imageModelId: str = Field(default="", max_length=120)


def _serialize(doc: dict[str, Any] | None) -> dict[str, Any]:
    source = doc or {}
    return {
        "enabled": source.get("enabled") is True,
        "configured": all(str(source.get(key) or "").strip() for key in (
            "llm_model_id",
            "image_model_id",
        )),
        "llmModelId": str(source.get("llm_model_id") or ""),
        "imageModelId": str(source.get("image_model_id") or ""),
        "updatedAt": utc_iso(source.get("updated_at")),
    }


async def _require_model(main_id: str, model_id: str, capability: str, label: str) -> None:
    if not str(model_id or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Presentation model unavailable: {capability}",
        )
    try:
        instance = await find_instance_by_id(model_id, main_id)
    except InvalidId as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Presentation model unavailable: {capability}",
        ) from exc
    capabilities = set(normalize_capabilities(instance.get("capabilities") or [])) if instance else set()
    if instance is None or instance.get("status") != "active" or capability not in capabilities:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Presentation model unavailable: {capability}",
        )


async def _models_available(main_id: str, settings: dict[str, Any]) -> bool:
    for key, capability in (("llmModelId", "chat"), ("imageModelId", "image_generation")):
        try:
            await _require_model(main_id, settings[key], capability, capability)
        except HTTPException:
            return False
    return True


@router.get("")
async def get_settings(
    current_user: dict[str, Any] = Depends(get_current_admin_user),
) -> dict[str, Any]:
    main_id = str(current_user.get("main_id") or "default")
    result = _serialize(await get_presentation_settings(main_id))
    result["available"] = await _models_available(main_id, result)
    return result


@router.put("")
async def put_settings(
    payload: PresentationSettingsPayload,
    current_user: dict[str, Any] = Depends(get_current_admin_user),
) -> dict[str, Any]:
    main_id = str(current_user.get("main_id") or "default")
    if payload.enabled:
        await _require_model(main_id, payload.llmModelId, "chat", "PPT content model")
        await _require_model(main_id, payload.imageModelId, "image_generation", "PPT image model")
    saved = await save_presentation_settings(
        main_id=main_id,
        enabled=payload.enabled,
        llm_model_id=payload.llmModelId,
        image_model_id=payload.imageModelId,
        updated_by=str(current_user.get("username") or ""),
    )
    result = _serialize(saved)
    result["available"] = await _models_available(main_id, result)
    return result


__all__ = ["PresentationSettingsPayload", "router"]
