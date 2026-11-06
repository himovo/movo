"""Requeue installed Skill environments after manager restarts or base-image changes."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import httpx

from app.core.db import get_db
from app.execution_isolation.skill_bundle import SkillBundle, cache_skill_bundle

from .archive_store import read_archive
from .prewarm import DEPENDENCY_FILES


LOG = logging.getLogger(__name__)
POLL_SECONDS = 30


async def _manager_identity(client: httpx.AsyncClient, base: str, headers: dict[str, str]) -> tuple[str, str]:
    response = await client.get(f"{base}/v1/skill-environments/base", headers=headers)
    response.raise_for_status()
    value = response.json()
    return str(value.get("instanceId") or ""), str(value.get("baseImageId") or "")


async def _installed_package_ids() -> set[str]:
    db = get_db()
    package_ids: set[str] = set()
    for collection in (db.skills, db.user_skills):
        rows = collection.find(
            {"package_id": {"$exists": True}, "deleted_at": None},
            {"package_id": 1, "pending_package.fields.package_id": 1},
        )
        async for row in rows:
            pending_fields = (row.get("pending_package") or {}).get("fields") or {}
            for value in (row.get("package_id"), pending_fields.get("package_id")):
                if value:
                    package_ids.add(str(value))
    return package_ids


async def _prepare_package(package: dict, client: httpx.AsyncClient, base: str, headers: dict[str, str]) -> None:
    if not any(item.get("path") in DEPENDENCY_FILES for item in package.get("files") or [] if isinstance(item, dict)):
        return
    digest = str(package.get("digest") or "")
    prefix = str(package.get("root_prefix") or "")
    root = Path(os.environ.get("MOVO_SANDBOX_WORKSPACE_ROOT", "/workspaces"))
    if not (root / "skill-cache" / digest / prefix / "SKILL.md").is_file():
        archive = await read_archive(get_db(), package)
        bundle = SkillBundle(name=str(package.get("slug") or ""), root_prefix=prefix, archive=archive, digest=digest)
        await asyncio.to_thread(cache_skill_bundle, bundle, root)
    response = await client.post(f"{base}/v1/skill-environments", json={"digest": digest}, headers=headers)
    response.raise_for_status()


async def reconcile_installed(client: httpx.AsyncClient, base: str, headers: dict[str, str]) -> bool:
    package_ids = sorted(await _installed_package_ids())
    db = get_db()
    semaphore = asyncio.Semaphore(8)
    failed = False

    async def prepare(package: dict) -> None:
        nonlocal failed
        async with semaphore:
            try:
                await _prepare_package(package, client, base, headers)
            except Exception:
                failed = True
                LOG.exception("Skill environment recovery failed for package %s", package.get("_id"))

    for offset in range(0, len(package_ids), 200):
        rows = db.skill_packages.find({"_id": {"$in": package_ids[offset:offset + 200]}})
        await asyncio.gather(*(prepare(package) async for package in rows))
    return not failed


async def monitor_installed_environments() -> None:
    base = os.environ.get("MOVO_SANDBOX_MANAGER_URL", "").strip().rstrip("/")
    token = os.environ.get("MOVO_SANDBOX_MANAGER_TOKEN", "")
    if not base or len(token) < 32:
        return
    headers = {"Authorization": f"Bearer {token}"}
    previous: tuple[str, str] | None = None
    async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
        while True:
            try:
                identity = await _manager_identity(client, base, headers)
                if identity[0] and identity[1] and identity != previous:
                    if await reconcile_installed(client, base, headers):
                        previous = identity
            except asyncio.CancelledError:
                raise
            except Exception:
                LOG.exception("Skill environment recovery check failed")
            await asyncio.sleep(POLL_SECONDS)
