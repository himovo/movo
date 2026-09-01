from __future__ import annotations

from typing import Any, Dict

from bson import ObjectId
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from app.api.endpoints.auth import _resolve_session_user
from app.core.db import get_db
from app.core.tenant import add_main_scope, resolve_main_id
from app.scheduled_tasks.models import ScheduledJobCreate, ScheduledJobUpdate
from app.scheduled_tasks.repository import RUNS, scheduled_task_repository, serialize_job
from app.scheduled_tasks.scheduler import scheduled_task_scheduler


router = APIRouter(prefix="/scheduled-jobs", tags=["scheduled-jobs"])


class ApiResponse(BaseModel):
    code: int = 0
    message: str | None = None
    data: object | None = None


async def _identity(authorization: str | None) -> tuple[str, str]:
    resolved = await _resolve_session_user(authorization if isinstance(authorization, str) else None)
    return resolve_main_id(resolved["main_id"]), str(resolved["user"].get("_id") or "")


async def _validate_session_target(payload: Dict[str, Any], *, main_id: str, user_id: str) -> None:
    if str(payload.get("session_mode") or "fixed") != "fixed":
        return
    session_id = str(payload.get("session_id") or "")
    if not ObjectId.is_valid(session_id):
        raise HTTPException(status_code=400, detail="目标会话无效")
    session = await get_db().chat_sessions.find_one(
        add_main_scope({"_id": ObjectId(session_id), "user_id": user_id}, main_id), {"_id": 1}
    )
    if not session:
        raise HTTPException(status_code=404, detail="目标会话不存在或无权访问")


def _safe_output_spec(value: Dict[str, Any]) -> Dict[str, Any]:
    blocked = {"user_id", "main_id", "task_id", "session_id", "message_id", "request_id"}
    return {key: item for key, item in dict(value or {}).items() if key not in blocked and not key.startswith("_")}


@router.get("", response_model=ApiResponse)
async def list_scheduled_jobs(authorization: str | None = Header(default=None)) -> ApiResponse:
    main_id, user_id = await _identity(authorization)
    return ApiResponse(message="ok", data=await scheduled_task_repository.list_jobs(main_id=main_id, user_id=user_id))


@router.post("", response_model=ApiResponse)
async def create_scheduled_job(payload: ScheduledJobCreate, authorization: str | None = Header(default=None)) -> ApiResponse:
    main_id, user_id = await _identity(authorization)
    raw = payload.model_dump()
    raw["output_spec"] = _safe_output_spec(raw.get("output_spec") or {})
    await _validate_session_target(raw, main_id=main_id, user_id=user_id)
    try:
        created = await scheduled_task_repository.create_job(raw, main_id=main_id, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApiResponse(message="created", data=created)


@router.patch("/{job_id}", response_model=ApiResponse)
async def update_scheduled_job(job_id: str, payload: ScheduledJobUpdate, authorization: str | None = Header(default=None)) -> ApiResponse:
    main_id, user_id = await _identity(authorization)
    current = await scheduled_task_repository.get_job(job_id, main_id=main_id, user_id=user_id)
    if not current:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    updates = payload.model_dump(exclude_unset=True)
    if "output_spec" in updates:
        updates["output_spec"] = _safe_output_spec(updates.get("output_spec") or {})
    merged = {**serialize_job(current), **updates}
    try:
        validated = ScheduledJobCreate.model_validate({key: merged.get(key) for key in ScheduledJobCreate.model_fields})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    normalized = validated.model_dump()
    normalized_updates = {key: normalized[key] for key in updates}
    await _validate_session_target(normalized, main_id=main_id, user_id=user_id)
    try:
        updated = await scheduled_task_repository.update_job(job_id, normalized_updates, main_id=main_id, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApiResponse(message="updated", data=updated)


@router.delete("/{job_id}", response_model=ApiResponse)
async def delete_scheduled_job(job_id: str, authorization: str | None = Header(default=None)) -> ApiResponse:
    main_id, user_id = await _identity(authorization)
    if not await scheduled_task_repository.delete_job(job_id, main_id=main_id, user_id=user_id):
        raise HTTPException(status_code=404, detail="定时任务不存在")
    return ApiResponse(message="deleted", data={"id": job_id})


@router.post("/{job_id}/run-now", response_model=ApiResponse)
async def run_scheduled_job_now(job_id: str, authorization: str | None = Header(default=None)) -> ApiResponse:
    main_id, user_id = await _identity(authorization)
    job = await scheduled_task_repository.get_job(job_id, main_id=main_id, user_id=user_id)
    if not job:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    run = await scheduled_task_scheduler.dispatch_now(job)
    if not run:
        raise HTTPException(status_code=409, detail="任务已在本次时间点触发")
    return ApiResponse(message="queued", data={"run_id": run["run_id"], "status": run["status"]})


@router.get("/{job_id}/runs", response_model=ApiResponse)
async def list_scheduled_job_runs(job_id: str, limit: int = Query(default=20, ge=1, le=100), authorization: str | None = Header(default=None)) -> ApiResponse:
    main_id, user_id = await _identity(authorization)
    if not await scheduled_task_repository.get_job(job_id, main_id=main_id, user_id=user_id):
        raise HTTPException(status_code=404, detail="定时任务不存在")
    cursor = get_db()[RUNS].find(
        {"job_id": job_id, "main_id": main_id, "owner_user_id": user_id}, {"_id": 0}
    ).sort("created_at", -1).limit(limit)
    return ApiResponse(message="ok", data=[row async for row in cursor])
