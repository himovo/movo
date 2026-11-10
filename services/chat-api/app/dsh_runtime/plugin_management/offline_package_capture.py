"""Record installed plugin dependencies in the shared offline package source."""

from __future__ import annotations

import logging
import os
import json
import re
from pathlib import Path

import httpx


LOG = logging.getLogger(__name__)


async def initialize_package_source() -> None:
    base = os.environ.get("MOVO_SANDBOX_MANAGER_URL", "").strip().rstrip("/")
    token = os.environ.get("MOVO_SANDBOX_MANAGER_TOKEN", "")
    if not base or not token:
        return
    try:
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            response = await client.get(f"{base}/v1/offline-packages",
                                        headers={"Authorization": f"Bearer {token}"})
            response.raise_for_status()
    except httpx.HTTPError:
        LOG.warning("Plugin offline package source is unavailable", exc_info=True)


def imported_plugin_record(spec: str) -> tuple[str, str]:
    if not re.fullmatch(r"(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*@[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?", spec):
        return "", ""
    name, version = spec.rsplit("@", 1)
    root = Path(os.environ.get("MOVO_OFFLINE_PACKAGE_ROOT", "/offline-packages"))
    for path in (root / "collections").glob("plugin-*.json"):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        digest = str(row.get("archiveDigest") or "")
        archive = root / "plugin-archives" / f"{digest}.tgz"
        if row.get("name") == name and row.get("version") == version and re.fullmatch(r"[0-9a-f]{64}", digest) and archive.is_file():
            return str(archive), str(row.get("dshVersion") or "")
    return "", ""


def imported_archive(spec: str) -> str:
    return imported_plugin_record(spec)[0]


async def record_plugin(name: str, version: str, archive_digest: str = "", dsh_version: str = "") -> None:
    base = os.environ.get("MOVO_SANDBOX_MANAGER_URL", "").strip().rstrip("/")
    token = os.environ.get("MOVO_SANDBOX_MANAGER_TOKEN", "")
    if not base or not token or not name or not version:
        return
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            if archive_digest:
                archive = Path(os.environ.get("DSH_RUNTIME_STORAGE_ROOT", "/data/dsh-runtime")) / "plugin-archives" / f"{archive_digest}.tgz"
                if archive.is_file():
                    async def chunks():
                        with archive.open("rb") as content:
                            while chunk := content.read(1024 * 1024):
                                yield chunk
                    uploaded = await client.post(f"{base}/v1/offline-packages/plugin-archives/{archive_digest}",
                                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/octet-stream"},
                                                 content=chunks())
                    uploaded.raise_for_status()
            response = await client.post(f"{base}/v1/offline-packages/collections/plugin",
                                         headers={"Authorization": f"Bearer {token}"},
                                         json={"name": name, "version": version,
                                               "archiveDigest": archive_digest if archive.is_file() else "",
                                               "dshVersion": dsh_version} if archive_digest else {
                                                   "name": name, "version": version, "dshVersion": dsh_version})
            response.raise_for_status()
    except (httpx.HTTPError, ValueError):
        LOG.warning("Plugin offline package collection could not be recorded", exc_info=True)
