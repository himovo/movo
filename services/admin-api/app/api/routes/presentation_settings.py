from __future__ import annotations

from typing import Any, Literal

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


router = APIRouter()


class PresentationSettingsPayload(BaseModel):
    generationMode: Literal["llm", "image_rebuild"] = "llm"
    llmModelId: str = Field(min_length=1, max_length=120)
    imageModelId: str = Field(default="", max_length=120)
    visionModelId: str = Field(default="", max_length=120)


def _serialize(doc: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "configured": bool(doc),
        "generationMode": str((doc or {}).get("generation_mode") or "llm"),
        "llmModelId": str((doc or {}).get("llm_model_id") or ""),
        "imageModelId": str((doc or {}).get("image_model_id") or ""),
        "visionModelId": str((doc or {}).get("vision_model_id") or ""),
        "updatedAt": utc_iso((doc or {}).get("updated_at")),
    }


async def _require_model(main_id: str, model_id: str, capability: str, label: str) -> None:
    if not str(model_id or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"请选择{label}",
        )
    try:
        instance = await find_instance_by_id(model_id, main_id)
    except InvalidId as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"请选择有效的{label}",
        ) from exc
    capabilities = set(instance.get("capabilities") or []) if instance else set()
    if instance is None or instance.get("status") != "active" or capability not in capabilities:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label}不存在、已禁用或不支持 {capability} 能力",
        )


@router.get("")
async def get_settings(
    current_user: dict[str, Any] = Depends(get_current_admin_user),
) -> dict[str, Any]:
    main_id = str(current_user.get("main_id") or "default")
    return _serialize(await get_presentation_settings(main_id))


@router.put("")
async def put_settings(
    payload: PresentationSettingsPayload,
    current_user: dict[str, Any] = Depends(get_current_admin_user),
) -> dict[str, Any]:
    main_id = str(current_user.get("main_id") or "default")
    await _require_model(main_id, payload.llmModelId, "chat", "PPT 内容与布局模型")
    if payload.generationMode == "image_rebuild":
        await _require_model(main_id, payload.imageModelId, "image_generation", "PPT 图片生成模型")
        await _require_model(main_id, payload.visionModelId, "vision", "PPT 视觉重建模型")
    saved = await save_presentation_settings(
        main_id=main_id,
        generation_mode=payload.generationMode,
        llm_model_id=payload.llmModelId,
        image_model_id=payload.imageModelId,
        vision_model_id=payload.visionModelId,
        updated_by=str(current_user.get("username") or ""),
    )
    return _serialize(saved)


__all__ = ["PresentationSettingsPayload", "router"]
