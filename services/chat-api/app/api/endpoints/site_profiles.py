from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AliasChoices, BaseModel, Field

from app.services.site_profiles import site_profile_service
from app.api.principal import ApiPrincipal, require_end_user_principal

router = APIRouter()


class ApiResponse(BaseModel):
    code: int = 0
    message: Optional[str] = None
    data: Optional[object] = None


class SiteProfileCreateRequest(BaseModel):
    user_id: str = Field(..., description="Owner user id")
    main_id: Optional[str] = Field(None, validation_alias=AliasChoices("main_id", "mainId"), description="Tenant / main account ID")
    name: str = Field(..., max_length=160)
    domain: Optional[str] = Field(default="", description="Bare host, e.g. oa.acme.com")
    entry_url: Optional[str] = Field(default="", description="Full login / landing URL")
    auth_method: Optional[str] = Field(default="", description="Free-form auth hint")
    hints: Optional[str] = Field(default="", description="Markdown hints for the planner LLM")
    visibility: Optional[str] = Field(default="private", description="private | team | global")


class SiteProfileUpdateRequest(BaseModel):
    user_id: str = Field(..., description="Owner user id")
    main_id: Optional[str] = Field(None, validation_alias=AliasChoices("main_id", "mainId"), description="Tenant / main account ID")
    name: Optional[str] = Field(None, max_length=160)
    domain: Optional[str] = None
    entry_url: Optional[str] = None
    auth_method: Optional[str] = None
    hints: Optional[str] = None
    visibility: Optional[str] = None


@router.get("/site-profiles", response_model=ApiResponse)
async def list_site_profiles(
    user_id: str = Query(..., alias="userId"),
    main_id: str = Query("default", alias="mainId"),
    main_id_snake: Optional[str] = Query(None, alias="main_id"),
    principal: ApiPrincipal = Depends(require_end_user_principal),
) -> ApiResponse:
    data = await site_profile_service.list_for_user(principal.user_id, main_id=principal.main_id)
    return ApiResponse(code=0, data=data)


@router.post("/site-profiles", response_model=ApiResponse)
async def create_site_profile(
    payload: SiteProfileCreateRequest,
    principal: ApiPrincipal = Depends(require_end_user_principal),
) -> ApiResponse:
    try:
        data = await site_profile_service.create(
            principal.user_id,
            name=payload.name,
            domain=payload.domain or "",
            entry_url=payload.entry_url or "",
            auth_method=payload.auth_method or "",
            hints=payload.hints or "",
            visibility=payload.visibility or "private",
            main_id=principal.main_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApiResponse(code=0, data=data)


@router.get("/site-profiles/{profile_id}", response_model=ApiResponse)
async def get_site_profile(
    profile_id: str,
    user_id: str = Query(..., alias="userId"),
    main_id: str = Query("default", alias="mainId"),
    main_id_snake: Optional[str] = Query(None, alias="main_id"),
    principal: ApiPrincipal = Depends(require_end_user_principal),
) -> ApiResponse:
    data = await site_profile_service.get(principal.user_id, profile_id, main_id=principal.main_id)
    if not data:
        raise HTTPException(status_code=404, detail="site profile not found")
    return ApiResponse(code=0, data=data)


@router.put("/site-profiles/{profile_id}", response_model=ApiResponse)
async def update_site_profile(
    profile_id: str,
    payload: SiteProfileUpdateRequest,
    principal: ApiPrincipal = Depends(require_end_user_principal),
) -> ApiResponse:
    updates = payload.model_dump(exclude={"user_id", "main_id"}, exclude_unset=True)
    data = await site_profile_service.update(
        principal.user_id,
        profile_id,
        updates,
        main_id=principal.main_id,
    )
    if data is None:
        raise HTTPException(status_code=404, detail="site profile not found or not owned by user")
    return ApiResponse(code=0, data=data)


@router.delete("/site-profiles/{profile_id}", response_model=ApiResponse)
async def delete_site_profile(
    profile_id: str,
    user_id: str = Query(..., alias="userId"),
    main_id: str = Query("default", alias="mainId"),
    main_id_snake: Optional[str] = Query(None, alias="main_id"),
    principal: ApiPrincipal = Depends(require_end_user_principal),
) -> ApiResponse:
    ok = await site_profile_service.delete(
        principal.user_id,
        profile_id,
        main_id=principal.main_id,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="site profile not found or not owned by user")
    return ApiResponse(code=0, data={"id": profile_id})
