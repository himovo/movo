"""Admin-only proxy for tenant DSH plugin installations."""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.api.deps import get_current_admin_user
from app.core.config import settings

router = APIRouter()


class InstallRequest(BaseModel):
    spec: str = Field(min_length=1, max_length=500)


class EnabledRequest(BaseModel):
    enabled: bool


def _forward(method: str, path: str, main_id: str, body: dict | None = None):
    base = str(settings.backend_base_url).rstrip("/")
    url = f"{base}/api/dsh-plugins/organization{path}?{urllib.parse.urlencode({'mainId': main_id})}"
    headers = {"Accept": "application/json", "X-MOVO-Service-Token": settings.backend_service_token}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=330) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            detail = json.load(exc).get("detail", "plugin_request_failed")
        except (ValueError, AttributeError):
            detail = "plugin_request_failed"
        raise HTTPException(status_code=exc.code, detail=detail) from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail="plugin_service_unavailable") from exc


def _forward_upload(main_id: str, filename: str, content: bytes):
    boundary = uuid.uuid4().hex
    safe_name = filename.replace('"', '').replace('\r', '').replace('\n', '')
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{safe_name}"\r\n'
        'Content-Type: application/gzip\r\n\r\n'
    ).encode() + content + f'\r\n--{boundary}--\r\n'.encode()
    base = str(settings.backend_base_url).rstrip("/")
    url = f"{base}/api/dsh-plugins/organization/upload?{urllib.parse.urlencode({'mainId': main_id})}"
    request = urllib.request.Request(url, data=body, method="POST", headers={
        "Accept": "application/json",
        "X-MOVO-Service-Token": settings.backend_service_token,
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    })
    try:
        with urllib.request.urlopen(request, timeout=330) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            detail = json.load(exc).get("detail", "plugin_request_failed")
        except (ValueError, AttributeError):
            detail = "plugin_request_failed"
        raise HTTPException(status_code=exc.code, detail=detail) from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail="plugin_service_unavailable") from exc


@router.get("")
async def list_plugins(admin=Depends(get_current_admin_user)):
    return await asyncio.to_thread(_forward, "GET", "", str(admin["main_id"]))


@router.post("/install")
async def install_plugin(body: InstallRequest, admin=Depends(get_current_admin_user)):
    return await asyncio.to_thread(_forward, "POST", "/install", str(admin["main_id"]), body.model_dump())


@router.post("/preflight")
async def preflight_plugin(body: InstallRequest, admin=Depends(get_current_admin_user)):
    return await asyncio.to_thread(_forward, "POST", "/preflight", str(admin["main_id"]), body.model_dump())


@router.post("/upload")
async def upload_plugin(file: UploadFile = File(...), admin=Depends(get_current_admin_user)):
    chunks = []
    total = 0
    while chunk := await file.read(1024 * 1024):
        total += len(chunk)
        if total > 100 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Plugin archive exceeds 100 MiB")
        chunks.append(chunk)
    return await asyncio.to_thread(_forward_upload, str(admin["main_id"]), file.filename or "plugin.tgz", b"".join(chunks))


@router.post("/{plugin_id}/verify")
async def verify_plugin(plugin_id: str, admin=Depends(get_current_admin_user)):
    return await asyncio.to_thread(_forward, "POST", f"/{plugin_id}/verify", str(admin["main_id"]))


@router.patch("/{plugin_id}/enabled")
async def set_enabled(plugin_id: str, body: EnabledRequest, admin=Depends(get_current_admin_user)):
    return await asyncio.to_thread(_forward, "PATCH", f"/{plugin_id}/enabled", str(admin["main_id"]), body.model_dump())


@router.delete("/{plugin_id}")
async def remove_plugin(plugin_id: str, admin=Depends(get_current_admin_user)):
    return await asyncio.to_thread(_forward, "DELETE", f"/{plugin_id}", str(admin["main_id"]))
