from __future__ import annotations

from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import get_current_admin_user
from app.repositories.model_repository import (
    find_instance_by_id,
    find_provider_by_id,
    update_instance_health,
)
from app.services.model_knowledge_connectivity import (
    ModelKnowledgeConnectivityError,
    run_saved_knowledge_model_test,
)


router = APIRouter()


class KnowledgeModelTestPayload(BaseModel):
    capability: str = Field(pattern=r"^(embedding|rerank)$")


@router.post("/instances/{instance_id}/test-knowledge")
async def test_knowledge_model_instance(
    instance_id: str,
    payload: KnowledgeModelTestPayload,
    current_user: dict = Depends(get_current_admin_user),
) -> dict[str, object]:
    main_id = str(current_user.get("main_id", "default"))
    try:
        instance = await find_instance_by_id(instance_id, main_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="模型配置ID无效") from exc
    if instance is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模型配置不存在")

    try:
        provider = await find_provider_by_id(str(instance.get("provider_id") or ""))
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="模型供应商ID无效") from exc
    if provider is None:
        return await _failed_result(instance_id, main_id, payload.capability, "模型供应商不存在")

    try:
        result = await run_saved_knowledge_model_test(instance, provider, capability=payload.capability)
    except ModelKnowledgeConnectivityError as exc:
        return await _failed_result(instance_id, main_id, payload.capability, str(exc))

    await update_instance_health(instance_id, main_id, "healthy", "")
    response: dict[str, object] = {
        "success": True,
        "status": "healthy",
        "message": result.message,
        "capability": payload.capability,
    }
    if result.dimension is not None:
        response["dimension"] = result.dimension
    return response


async def _failed_result(instance_id: str, main_id: str, capability: str, message: str) -> dict[str, object]:
    await update_instance_health(instance_id, main_id, "failed", message)
    return {
        "success": False,
        "status": "failed",
        "message": message,
        "capability": capability,
    }
