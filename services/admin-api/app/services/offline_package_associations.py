"""Resolve local Skill names for exported dependency collections."""

from __future__ import annotations

from app.core.db import get_db


async def attach_skill_names(inventory: dict, main_id: str) -> dict:
    collections = inventory.get("collections")
    if not isinstance(collections, list):
        return inventory
    digests = {str(item.get("digest") or "") for item in collections if item.get("kind") == "skill"}
    digests.discard("")
    if not digests:
        return inventory
    rows = await get_db().skills.find(
        {"main_id": main_id, "deleted_at": None, "package_digest": {"$in": list(digests)}},
        {"_id": 1, "name": 1, "package_digest": 1},
    ).to_list(length=2000)
    names = {str(row.get("package_digest") or ""): {"skillId": str(row["_id"]),
                                                     "skillName": str(row.get("name") or "")}
             for row in rows}
    for item in collections:
        item.update(names.get(str(item.get("digest") or ""), {}))
    return inventory
