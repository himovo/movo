"""Admin access to the sandbox dependency package inventory."""

from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.operations_access import get_system_operator
from app.services.offline_package_associations import attach_skill_names


router = APIRouter()


def _connection() -> tuple[str, dict[str, str]]:
    base = os.environ.get("MOVO_SANDBOX_MANAGER_URL", "").strip().rstrip("/")
    token = os.environ.get("MOVO_SANDBOX_MANAGER_TOKEN", "")
    if not base or not token:
        raise HTTPException(status_code=503, detail="sandbox_manager_unavailable")
    return base, {"Authorization": f"Bearer {token}"}


def _json(method: str, path: str, body: dict | None = None) -> dict:
    base, headers = _connection()
    try:
        with httpx.Client(timeout=30, trust_env=False) as client:
            response = client.request(method, f"{base}/v1/offline-packages{path}", headers=headers, json=body)
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="offline_package_store_unavailable") from exc


class OfflineMode(BaseModel):
    offlineOnly: bool


@router.get("")
async def inventory(operator: dict = Depends(get_system_operator)) -> dict:
    return await attach_skill_names(_json("GET", ""), str(operator.get("main_id") or ""))


@router.put("/mode")
async def mode(value: OfflineMode, operator: dict = Depends(get_system_operator)) -> dict:
    return await attach_skill_names(_json("PUT", "/mode", value.model_dump()), str(operator.get("main_id") or ""))


@router.get("/export")
def export(records: str = Query(default="", max_length=5000), _: dict = Depends(get_system_operator)) -> StreamingResponse:
    base, headers = _connection()
    client = httpx.Client(timeout=3600, trust_env=False)
    stream = client.stream("GET", f"{base}/v1/offline-packages/export", headers=headers,
                           params={"records": records} if records else None)
    try:
        response = stream.__enter__()
        response.raise_for_status()
    except httpx.HTTPError as exc:
        stream.__exit__(None, None, None)
        client.close()
        raise HTTPException(status_code=503, detail="offline_package_store_unavailable") from exc

    def chunks():
        try:
            yield from response.iter_bytes()
        finally:
            stream.__exit__(None, None, None)
            client.close()

    return StreamingResponse(chunks(), media_type="application/zip", headers={
        "Content-Disposition": 'attachment; filename="movo-offline-packages.zip"',
    })


@router.post("/import")
async def import_archive(request: Request, operator: dict = Depends(get_system_operator)) -> dict:
    base, headers = _connection()
    try:
        async with httpx.AsyncClient(timeout=3600, trust_env=False) as client:
            response = await client.post(f"{base}/v1/offline-packages/import", headers={**headers, "Content-Type": "application/octet-stream"},
                                         content=request.stream())
            if response.status_code == 400:
                raise HTTPException(status_code=400, detail=response.json().get("detail", "invalid_package_archive"))
            response.raise_for_status()
            return await attach_skill_names(response.json(), str(operator.get("main_id") or ""))
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="offline_package_store_unavailable") from exc
