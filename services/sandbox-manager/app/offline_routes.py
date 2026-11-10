"""Authenticated transfer endpoints for reusable dependency packages."""

from __future__ import annotations

import os
import hashlib
import re
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.background import BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .offline_package_store import MAX_ARCHIVE_BYTES, OfflinePackageStore
from .offline_collections import record_plugin


router = APIRouter(prefix="/v1/offline-packages")


def authorized(authorization: str | None = Header(default=None)) -> None:
    from .main import _authorize
    _authorize(authorization)


class OfflineMode(BaseModel):
    offlineOnly: bool


class PluginCollection(BaseModel):
    name: str
    version: str
    archiveDigest: str = ""
    dshVersion: str = ""


@router.get("")
def inventory(_: None = Depends(authorized)) -> dict:
    return OfflinePackageStore().inventory()


@router.put("/mode")
def mode(value: OfflineMode, _: None = Depends(authorized)) -> dict:
    return OfflinePackageStore().set_offline(value.offlineOnly)


@router.post("/collections/plugin")
def plugin_collection(value: PluginCollection, _: None = Depends(authorized)) -> dict:
    if value.archiveDigest and not re.fullmatch(r"[0-9a-f]{64}", value.archiveDigest):
        raise HTTPException(status_code=400, detail="Invalid plugin archive digest")
    return record_plugin(OfflinePackageStore().root, name=value.name, version=value.version,
                         archive_digest=value.archiveDigest, dsh_version=value.dshVersion)


@router.post("/plugin-archives/{digest}")
async def plugin_archive(digest: str, request: Request, _: None = Depends(authorized)) -> dict:
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise HTTPException(status_code=400, detail="Invalid plugin archive digest")
    target = OfflinePackageStore().root / "plugin-archives" / f"{digest}.tgz"
    handle, name = tempfile.mkstemp(prefix="plugin-", suffix=".tgz", dir=target.parent)
    temporary = Path(name)
    checksum = hashlib.sha256()
    try:
        with os.fdopen(handle, "wb") as output:
            size = 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 100 * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="Plugin archive exceeds the size limit")
                checksum.update(chunk)
                output.write(chunk)
        if checksum.hexdigest() != digest:
            raise HTTPException(status_code=400, detail="Plugin archive digest mismatch")
        if not target.exists():
            os.replace(temporary, target)
            target.chmod(0o644)
        return {"digest": digest, "size": size}
    finally:
        temporary.unlink(missing_ok=True)


@router.get("/export")
def export(background: BackgroundTasks, records: str = Query(default="", max_length=5000),
           _: None = Depends(authorized)) -> FileResponse:
    handle, name = tempfile.mkstemp(prefix="movo-offline-", suffix=".zip", dir=OfflinePackageStore().root)
    os.close(handle)
    path = Path(name)
    try:
        record_ids = set(records.split(",")) if records else None
        if record_ids is not None and (len(record_ids) > 100 or any(len(value) != 32 or any(char not in "0123456789abcdef" for char in value) for value in record_ids)):
            raise ValueError("Invalid preparation record selection")
        OfflinePackageStore().export_to(path, record_ids)
    except ValueError as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        path.unlink(missing_ok=True)
        raise
    background.add_task(path.unlink, missing_ok=True)
    return FileResponse(path, filename="movo-offline-packages.zip", background=background)


@router.post("/import")
async def import_archive(request: Request, _: None = Depends(authorized)) -> dict:
    handle, name = tempfile.mkstemp(prefix="movo-offline-import-", suffix=".zip", dir=OfflinePackageStore().root)
    path = Path(name)
    try:
        with os.fdopen(handle, "wb") as output:
            size = 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_ARCHIVE_BYTES:
                    raise HTTPException(status_code=413, detail="Offline package archive exceeds the size limit")
                output.write(chunk)
        try:
            return OfflinePackageStore().import_archive(path)
        except (ValueError, KeyError, OSError, zipfile.BadZipFile) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        path.unlink(missing_ok=True)
