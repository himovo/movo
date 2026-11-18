"""Read-only administrator view of the optional sandbox control plane."""

from __future__ import annotations

from typing import Literal

import asyncio
import json
import os
import urllib.error
import urllib.request

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_current_admin_user


router = APIRouter()


class UpdateQueueRequest(BaseModel):
    runtime_mode: Literal["on_demand", "forced"] | None = None
    plugin_idle_seconds: int | None = Field(default=None, ge=0, le=604800)
    max_pending: int | None = Field(default=None, ge=0, le=100)
    capacity: int | None = Field(default=None, ge=1, le=100)


def _manager_request(method: str, path: str, body: dict | None = None) -> dict:
    base = os.environ.get("MOVO_SANDBOX_MANAGER_URL", "").strip().rstrip("/")
    token = os.environ.get("MOVO_SANDBOX_MANAGER_TOKEN", "")
    if not base or not token:
        raise RuntimeError("Sandbox manager is disabled")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        f"{base}{path}", method=method, data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=3) as response:
        return json.load(response)


def _status() -> dict:
    if not os.environ.get("MOVO_SANDBOX_MANAGER_URL", "").strip():
        return {"enabled": False, "healthy": False}
    try:
        data = _manager_request("GET", "/health")
    except (OSError, urllib.error.URLError, ValueError):
        return {"enabled": True, "healthy": False}
    return {
        "enabled": True,
        "healthy": data.get("ok") is True,
        "running": int(data.get("running", 0)),
        "pending": int(data.get("pending", 0)),
        "capacity": int(data.get("capacity", 0)),
        "task_capacity": int(data.get("resident_capacity", data.get("task_capacity", 10))),
        "resident_containers": int(data.get("resident_containers", 0)),
        "max_pending": int(data.get("max_pending", 0)),
        "plugin_runtimes": int(data.get("plugin_runtimes", 0)),
        "runtime_mode": data.get("runtime_mode", "on_demand"),
        "plugin_idle_seconds": int(data.get("plugin_idle_seconds", 900)),
    }


@router.get("/status")
async def get_status(_admin=Depends(get_current_admin_user)) -> dict:
    return await asyncio.to_thread(_status)


@router.put("/settings")
async def update_settings(body: UpdateQueueRequest, _admin=Depends(get_current_admin_user)) -> dict:
    try:
        return await asyncio.to_thread(_manager_request, "PUT", "/v1/settings", body.model_dump(exclude_none=True))
    except (OSError, urllib.error.URLError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="sandbox_manager_unavailable") from exc
