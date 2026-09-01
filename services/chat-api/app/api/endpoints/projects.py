"""Durable metadata for desktop Code projects.

The local DSH workspace registry owns the filesystem binding.  This endpoint
persists the user-visible project record separately, so an empty project is
not dependent on a first chat session being created.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from app.api.endpoints.auth import _resolve_session_user
from app.core.db import get_db
from app.core.tenant import resolve_main_id


router = APIRouter(tags=["projects"])


class DesktopProjectCreate(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=200)
    worktree: bool = False


class ApiResponse(BaseModel):
    code: int = 0
    message: str | None = None
    data: object | None = None


def _serialize_project(doc: dict) -> dict:
    return {
        "workspace_id": str(doc.get("workspace_id") or ""),
        "title": str(doc.get("title") or ""),
        "worktree": bool(doc.get("worktree")),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


async def _identity(authorization: str | None) -> tuple[str, str]:
    resolved = await _resolve_session_user(authorization if isinstance(authorization, str) else None)
    return resolve_main_id(resolved["main_id"]), str(resolved["user"].get("_id") or "")


@router.post("/projects", response_model=ApiResponse)
async def create_desktop_project(
    payload: DesktopProjectCreate,
    authorization: str | None = Header(default=None),
):
    main_id, user_id = await _identity(authorization)
    now = datetime.utcnow()
    scope = {"main_id": main_id, "user_id": user_id, "workspace_id": payload.workspace_id}
    await get_db().desktop_projects.update_one(
        scope,
        {
            "$set": {"title": payload.title.strip(), "worktree": payload.worktree, "updated_at": now},
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    project = await get_db().desktop_projects.find_one(scope)
    return ApiResponse(data=_serialize_project(project or {**scope, "title": payload.title, "worktree": payload.worktree, "created_at": now, "updated_at": now}))


@router.get("/projects", response_model=ApiResponse)
async def list_desktop_projects(authorization: str | None = Header(default=None)):
    main_id, user_id = await _identity(authorization)
    cursor = get_db().desktop_projects.find({"main_id": main_id, "user_id": user_id}).sort("updated_at", -1)
    return ApiResponse(data=[_serialize_project(item) async for item in cursor])
