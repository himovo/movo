"""Attach tenant-scoped Skill and plugin owners to Docker image inventory."""

from __future__ import annotations

import asyncio

from app.core.db import get_db
from app.services.skill_package_proxy import organization_skill_dependency_status


async def _missing_skill_states(images: list[dict], main_id: str) -> dict[str, str]:
    semaphore = asyncio.Semaphore(8)

    async def read(image: dict) -> tuple[str, str]:
        async with semaphore:
            try:
                result = await asyncio.to_thread(
                    organization_skill_dependency_status,
                    main_id=main_id, skill_id=image["owners"][0]["id"],
                )
                return image["digest"], str(result.get("status") or "unavailable")
            except Exception:
                return image["digest"], "unavailable"

    missing = [image for image in images if image.get("kind") == "skill"
               and not image.get("available") and image.get("owners")]
    return dict(await asyncio.gather(*(read(image) for image in missing)))


async def attach(status: dict, main_id: str) -> dict:
    images = status.get("sandboxImages")
    if not isinstance(images, list):
        return status
    db = get_db()
    skills = await db.skills.find(
        {"main_id": main_id, "deleted_at": None, "package_digest": {"$exists": True}},
        {"_id": 1, "name": 1, "package_digest": 1},
    ).to_list(length=2000)
    plugins = await db.dsh_plugin_installations.find(
        {"main_id": main_id, "owner_user_id": "", "engine": "dsh"},
        {"_id": 1, "name": 1},
    ).to_list(length=2000)
    by_digest: dict[str, list[dict]] = {}
    for skill in skills:
        by_digest.setdefault(str(skill.get("package_digest") or ""), []).append({
            "id": str(skill["_id"]), "name": str(skill.get("name") or ""),
        })
    for image in images:
        if image.get("kind") == "skill":
            image["owners"] = by_digest.get(str(image.get("digest") or ""), [])
            image["current"] = bool(image["owners"])
        elif image.get("kind") == "plugin":
            image["owners"] = [{"id": str(item["_id"]), "name": str(item.get("name") or "")} for item in plugins]
            image["current"] = True
        else:
            image["owners"] = []
            image["current"] = True
    states = await _missing_skill_states(images, main_id)
    for image in images:
        if image.get("kind") == "skill" and not image.get("available"):
            image["preparationStatus"] = states.get(str(image.get("digest") or ""), "missing")
    return status
