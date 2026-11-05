"""Admin image archive transfer via the sandbox manager."""

from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.operations_access import get_system_operator


router = APIRouter()


def _connection() -> tuple[str, dict[str, str]]:
    base = os.environ.get("MOVO_SANDBOX_MANAGER_URL", "").strip().rstrip("/")
    token = os.environ.get("MOVO_SANDBOX_MANAGER_TOKEN", "")
    if not base or not token:
        raise HTTPException(status_code=503, detail="sandbox_manager_unavailable")
    return base, {"Authorization": f"Bearer {token}"}


@router.get("/export")
def export(name: str, _: dict = Depends(get_system_operator)) -> StreamingResponse:
    base, headers = _connection()
    client = httpx.Client(timeout=3600, trust_env=False)
    stream = client.stream("GET", f"{base}/v1/sandbox-images/export", params={"name": name}, headers=headers)
    try:
        response = stream.__enter__()
        response.raise_for_status()
    except httpx.HTTPError as exc:
        stream.__exit__(None, None, None)
        client.close()
        raise HTTPException(status_code=400 if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 400 else 503,
                            detail="sandbox_image_export_unavailable") from exc

    def chunks():
        try:
            yield from response.iter_bytes()
        finally:
            stream.__exit__(None, None, None)
            client.close()

    return StreamingResponse(chunks(), media_type="application/zip", headers={
        "Content-Disposition": 'attachment; filename="movo-sandbox-image.zip"',
    })


@router.post("/import")
async def import_archive(request: Request, _: dict = Depends(get_system_operator)) -> dict:
    base, headers = _connection()
    try:
        async with httpx.AsyncClient(timeout=3600, trust_env=False) as client:
            response = await client.post(f"{base}/v1/sandbox-images/import", headers={**headers, "Content-Type": "application/octet-stream"},
                                         content=request.stream())
            if response.status_code == 400:
                raise HTTPException(status_code=400, detail=response.json().get("detail", "invalid_image_archive"))
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="sandbox_manager_unavailable") from exc
