"""Authenticated image archive transfer endpoints."""

from __future__ import annotations

import os
import tempfile
import tarfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.background import BackgroundTasks
from fastapi.responses import FileResponse

from .docker_engine import DockerEngine
from .image_archive import MAX_IMAGE_BYTES, export_image, import_image
from .storage_paths import manager_state_root


router = APIRouter(prefix="/v1/sandbox-images")


def authorized(authorization: str | None = Header(default=None)) -> None:
    from .main import _authorize
    _authorize(authorization)


@router.get("/export")
def export(background: BackgroundTasks, name: str = Query(max_length=300),
           _: None = Depends(authorized)) -> FileResponse:
    manager_state_root().mkdir(parents=True, exist_ok=True)
    handle, filename = tempfile.mkstemp(prefix="movo-image-", suffix=".zip", dir=manager_state_root())
    os.close(handle)
    path = Path(filename)
    try:
        export_image(DockerEngine(), name, path)
    except (ValueError, OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background.add_task(path.unlink, missing_ok=True)
    return FileResponse(path, filename="movo-sandbox-image.zip", background=background)


@router.post("/import")
async def import_archive(request: Request, _: None = Depends(authorized)) -> dict:
    manager_state_root().mkdir(parents=True, exist_ok=True)
    handle, filename = tempfile.mkstemp(prefix="movo-image-import-", suffix=".zip", dir=manager_state_root())
    path = Path(filename)
    try:
        with os.fdopen(handle, "wb") as target:
            size = 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_IMAGE_BYTES:
                    raise HTTPException(status_code=413, detail="Image archive exceeds the size limit")
                target.write(chunk)
        try:
            return import_image(DockerEngine(), path)
        except (ValueError, OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        path.unlink(missing_ok=True)
