from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header
from pydantic import BaseModel

from app.api.endpoints.auth import _resolve_session_user
from app.core.quota_policy import get_quota_summary

router = APIRouter()


class ApiResponse(BaseModel):
    code: int = 0
    message: Optional[str] = None
    data: object | None = None


@router.get("/quota/me", response_model=ApiResponse)
async def get_my_quota(authorization: str | None = Header(default=None)) -> ApiResponse:
    resolved = await _resolve_session_user(authorization)
    data = await get_quota_summary(str(resolved["main_id"]), resolved["user"])
    return ApiResponse(code=0, message="success", data=data)
