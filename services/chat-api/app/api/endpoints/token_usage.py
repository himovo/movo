from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, Query
from pydantic import BaseModel

from app.api.endpoints.auth import _resolve_session_user
from app.core.tenant import resolve_main_id
from app.services.token_usage_service import token_usage_service

router = APIRouter()


class ApiResponse(BaseModel):
    code: int = 0
    message: Optional[str] = None
    data: object | None = None


@router.get("/token-usage", response_model=ApiResponse)
async def list_token_usage(
    user_id: str = Query("", alias="userId"),
    main_id: Optional[str] = Query(None, alias="mainId"),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    q: str = Query(""),
    stage: str = Query(""),
    status: str = Query(""),
    authorization: str | None = Header(default=None),
) -> ApiResponse:
    resolved = await _resolve_session_user(authorization)
    current_user_id = str(resolved["user"].get("_id") or "")
    scoped_main_id = resolve_main_id(main_id or resolved.get("main_id"))
    data = await token_usage_service.list_logs(
        user_id=current_user_id or str(user_id or ""),
        main_id=scoped_main_id,
        offset=offset,
        limit=limit,
        query=q,
        stage=stage,
        status=status,
    )
    return ApiResponse(code=0, message="success", data=data)
