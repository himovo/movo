from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.services.external_tools import external_tool_registry, external_tool_service
from app.governance.position_policy import MongoEmployeePolicyResolver
from app.api.principal import require_api_principal

router = APIRouter(dependencies=[Depends(require_api_principal)])


class ApiResponse(BaseModel):
    code: int = 0
    message: Optional[str] = None
    data: Optional[object] = None


class ToolTestPayload(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)


class ToolDraftTestPayload(BaseModel):
    tool: dict[str, Any] = Field(default_factory=dict)
    input: dict[str, Any] = Field(default_factory=dict)


class ToolDescriptionGeneratePayload(BaseModel):
    name: str = Field(default="", min_length=1, max_length=120)
    type: str = Field(default="http")
    existingDescription: str = Field(default="")


class ToolPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: str = Field(default="http")
    description: str = ""
    usageHint: str = ""
    tags: list[str] = Field(default_factory=list)
    status: str = "disabled"
    config: dict[str, Any] = Field(default_factory=dict)


def _require_user_id(user_id: str) -> str:
    uid = str(user_id or "").strip()
    if not uid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing userId")
    return uid


async def _require_tool_access(main_id: str, user_id: str, tool_id: str | None = None):
    policy = await MongoEmployeePolicyResolver().resolve(main_id, user_id)
    if tool_id is not None and not policy.allows_external_tool(tool_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前岗位未开通该工具")
    return policy


@router.get("/external-tools/my", response_model=ApiResponse)
async def list_user_external_tools(
    user_id: str = Query("", alias="userId"),
    main_id: str = Query("default", alias="mainId"),
) -> ApiResponse:
    uid = _require_user_id(user_id)
    data = await external_tool_service.list(main_id, scope="user", owner_user_id=uid)
    policy = await _require_tool_access(main_id, uid)
    data = [row for row in data if policy.allows_external_tool(str(row.get("id") or row.get("_id") or ""))]
    return ApiResponse(data=data)


@router.post("/external-tools/my", response_model=ApiResponse)
async def create_user_external_tool(
    payload: ToolPayload,
    user_id: str = Query("", alias="userId"),
    main_id: str = Query("default", alias="mainId"),
) -> ApiResponse:
    uid = _require_user_id(user_id)
    policy = await _require_tool_access(main_id, uid)
    if policy.tool_access_mode != "all":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前岗位不能创建新的工具连接")
    try:
        data = await external_tool_service.create(payload.model_dump(), main_id, scope="user", owner_user_id=uid)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ApiResponse(data=data)


@router.get("/external-tools/my/{tool_id}", response_model=ApiResponse)
async def get_user_external_tool(
    tool_id: str,
    user_id: str = Query("", alias="userId"),
    main_id: str = Query("default", alias="mainId"),
) -> ApiResponse:
    uid = _require_user_id(user_id)
    await _require_tool_access(main_id, uid, tool_id)
    data = await external_tool_service.get(tool_id, main_id, scope="user", owner_user_id=uid)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工具连接不存在")
    return ApiResponse(data=data)


@router.put("/external-tools/my/{tool_id}", response_model=ApiResponse)
async def update_user_external_tool(
    tool_id: str,
    payload: ToolPayload,
    user_id: str = Query("", alias="userId"),
    main_id: str = Query("default", alias="mainId"),
) -> ApiResponse:
    uid = _require_user_id(user_id)
    await _require_tool_access(main_id, uid, tool_id)
    try:
        data = await external_tool_service.update(tool_id, payload.model_dump(), main_id, scope="user", owner_user_id=uid)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工具连接不存在")
    return ApiResponse(data=data)


@router.patch("/external-tools/my/{tool_id}", response_model=ApiResponse)
async def patch_user_external_tool(
    tool_id: str,
    payload: dict[str, Any],
    user_id: str = Query("", alias="userId"),
    main_id: str = Query("default", alias="mainId"),
) -> ApiResponse:
    uid = _require_user_id(user_id)
    await _require_tool_access(main_id, uid, tool_id)
    try:
        data = await external_tool_service.update(tool_id, payload, main_id, scope="user", owner_user_id=uid)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工具连接不存在")
    return ApiResponse(data=data)


@router.delete("/external-tools/my/{tool_id}", response_model=ApiResponse)
async def delete_user_external_tool(
    tool_id: str,
    user_id: str = Query("", alias="userId"),
    main_id: str = Query("default", alias="mainId"),
) -> ApiResponse:
    uid = _require_user_id(user_id)
    await _require_tool_access(main_id, uid, tool_id)
    ok = await external_tool_service.delete(tool_id, main_id, scope="user", owner_user_id=uid)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工具连接不存在")
    return ApiResponse(data={"id": tool_id})


@router.get("/external-tools/registry", response_model=ApiResponse)
async def list_external_tool_registry(main_id: str = Query("default", alias="mainId")) -> ApiResponse:
    data = await external_tool_registry.list_enabled_descriptors(main_id)
    return ApiResponse(data=data)


@router.post("/external-tools/{tool_id}/test", response_model=ApiResponse)
async def test_external_tool(tool_id: str, payload: ToolTestPayload, main_id: str = Query("default", alias="mainId")) -> ApiResponse:
    try:
        data = await external_tool_service.test(tool_id, payload.input, main_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ApiResponse(data=data)


@router.post("/external-tools/my/{tool_id}/test", response_model=ApiResponse)
async def test_user_external_tool(
    tool_id: str,
    payload: ToolTestPayload,
    user_id: str = Query("", alias="userId"),
    main_id: str = Query("default", alias="mainId"),
) -> ApiResponse:
    uid = _require_user_id(user_id)
    await _require_tool_access(main_id, uid, tool_id)
    data = await external_tool_service.test(tool_id, payload.input, main_id, scope="user", owner_user_id=uid)
    return ApiResponse(data=data)


@router.post("/external-tools/test-draft", response_model=ApiResponse)
async def test_draft_external_tool(payload: ToolDraftTestPayload, main_id: str = Query("default", alias="mainId")) -> ApiResponse:
    data = await external_tool_service.test_draft(payload.tool, payload.input, main_id)
    return ApiResponse(data=data)


@router.post("/external-tools/{tool_id}/discover", response_model=ApiResponse)
async def discover_mcp_tools(tool_id: str, main_id: str = Query("default", alias="mainId")) -> ApiResponse:
    try:
        data = await external_tool_service.discover_mcp_tools(tool_id, main_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ApiResponse(data=data)


@router.post("/external-tools/my/{tool_id}/discover", response_model=ApiResponse)
async def discover_user_mcp_tools(
    tool_id: str,
    user_id: str = Query("", alias="userId"),
    main_id: str = Query("default", alias="mainId"),
) -> ApiResponse:
    uid = _require_user_id(user_id)
    await _require_tool_access(main_id, uid, tool_id)
    try:
        data = await external_tool_service.discover_mcp_tools(tool_id, main_id, scope="user", owner_user_id=uid)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ApiResponse(data=data)


@router.post("/external-tools/generate-description", response_model=ApiResponse)
async def generate_external_tool_description(
    payload: ToolDescriptionGeneratePayload,
    main_id: str = Query("default", alias="mainId"),
) -> ApiResponse:
    try:
        data = await external_tool_service.generate_description(
            name=payload.name,
            tool_type=payload.type,
            existing_description=payload.existingDescription,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ApiResponse(data=data)
