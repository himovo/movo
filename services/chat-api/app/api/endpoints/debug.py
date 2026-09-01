from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.config import get_settings
from app.infrastructure.runtime_services import env_manager, runtime_kpi_store
from app.api.principal import require_end_user_principal


async def require_debug_mode() -> None:
    if not get_settings().DEBUG:
        raise HTTPException(status_code=404, detail="Not found")


router = APIRouter(
    dependencies=[Depends(require_debug_mode), Depends(require_end_user_principal)]
)


class ApiResponse(BaseModel):
    code: int = 0
    message: str | None = None
    data: object | None = None


@router.get("/debug/llm-config", response_model=ApiResponse)
async def llm_config() -> ApiResponse:
    settings = get_settings()
    data = {
        "USE_AZURE": settings.USE_AZURE,
        "AZURE_OPENAI_ENDPOINT": settings.AZURE_OPENAI_ENDPOINT,
        "AZURE_OPENAI_API_VERSION": settings.AZURE_OPENAI_API_VERSION,
        "AZURE_DEPLOYMENT_NAME": settings.AZURE_DEPLOYMENT_NAME,
        "AZURE_DEPLOYMENT_CHAT": settings.AZURE_DEPLOYMENT_CHAT,
        "AZURE_DEPLOYMENT_GENERAL": settings.AZURE_DEPLOYMENT_GENERAL,
        "AZURE_DEPLOYMENT_CODING": settings.AZURE_DEPLOYMENT_CODING,
        "OPENAI_BASE_URL": settings.OPENAI_BASE_URL,
        "OPENAI_MODEL": settings.OPENAI_MODEL,
        "OPENAI_MODEL_GENERAL": settings.OPENAI_MODEL_GENERAL,
        "OPENAI_MODEL_CHAT": settings.OPENAI_MODEL_CHAT,
        "OPENAI_MODEL_CODING": settings.OPENAI_MODEL_CODING,
        "PIPELINE_MODE": settings.PIPELINE_MODE,
    }
    return ApiResponse(code=0, message="success", data=data)


@router.get("/debug/runtime-kpi", response_model=ApiResponse)
async def runtime_kpi() -> ApiResponse:
    data = await runtime_kpi_store.snapshot()
    return ApiResponse(code=0, message="success", data=data)


@router.get("/debug/env-metrics", response_model=ApiResponse)
async def env_metrics() -> ApiResponse:
    data = await env_manager.metrics()
    return ApiResponse(code=0, message="success", data=data)
