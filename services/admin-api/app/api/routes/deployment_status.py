"""Administrator-only deployment inventory endpoint."""

from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_admin_user


router = APIRouter()


def _read_status() -> dict:
    base = os.environ.get("MOVO_DEPLOYMENT_STATUS_URL", "").strip().rstrip("/")
    token = os.environ.get("MOVO_SANDBOX_MANAGER_TOKEN", "")
    if not base or not token:
        raise RuntimeError("Deployment observer is unavailable")
    request = urllib.request.Request(f"{base}/status", headers={"Authorization": f"Bearer {token}"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=5) as response:
        return json.load(response)


@router.get("/status")
async def status(_admin=Depends(get_current_admin_user)) -> dict:
    try:
        return await asyncio.to_thread(_read_status)
    except (RuntimeError, OSError, urllib.error.URLError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="deployment_status_unavailable") from exc
