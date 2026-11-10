from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId

from app.core.db import get_db


def _public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["_id"]),
        "name": row["name"],
        "version": row["version"],
        "spec": row["spec"],
        "description": row.get("description", ""),
        "tool_names": row.get("tool_names", []),
        "enabled": bool(row.get("enabled")),
        "scope": "personal" if row.get("owner_user_id") else "organization",
        "engine": row.get("engine", "dsh"),
        "source": row.get("source", "manual"),
        "archive_id": row.get("archive_id", ""),
        "availability": row.get("availability") or {"status": "unverified", "reason": "legacy_not_assessed", "checks": {}},
        "updatedAt": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


class PluginInstallationRepository:
    async def list_enabled_installations(self) -> list[dict[str, Any]]:
        return await get_db().dsh_plugin_installations.find({
            "engine": "dsh", "enabled": True,
        }).to_list(length=None)

    async def restore_legacy_surface_pending(self, dsh_version: str) -> None:
        await get_db().dsh_plugin_installations.update_many({
            "engine": "dsh", "enabled": True,
            "availability.status": "unverified",
            "availability.reason": "revalidation_in_progress",
            "availability.dsh_version": dsh_version,
            "availability.target_dsh_version": dsh_version,
            "availability.release_compatibility_checked": True,
            "availability.checks.runtime": True,
            "availability.checks.session": True,
            "availability.capabilities.clientModules": {"$elemMatch": {"conversationView": {"$exists": False}}},
        }, {"$set": {
            "availability.status": "runtime_active",
            "availability.reason": "other_capabilities_available",
        }, "$unset": {"availability.revalidation_started_at": ""}})

    async def clear_surface_refresh(self, row: dict[str, Any]) -> None:
        await get_db().dsh_plugin_installations.update_one({
            "_id": row["_id"], "version": row["version"], "spec": row["spec"],
        }, {"$unset": {"availability.surface_refresh_started_at": ""}})

    async def mark_revalidation_pending(self, row: dict[str, Any], dsh_version: str,
                                        surface_only: bool = False) -> bool:
        now = datetime.now(timezone.utc)
        if surface_only:
            result = await get_db().dsh_plugin_installations.update_one({
                "_id": row["_id"], "engine": "dsh", "enabled": True,
                "version": row["version"], "spec": row["spec"],
                "availability.status": {"$in": ["session_exposed", "runtime_active", "verified"]},
                "availability.dsh_version": dsh_version,
                "availability.capabilities.clientModules": {"$elemMatch": {"conversationView": {"$exists": False}}},
                "$or": [
                    {"availability.surface_refresh_started_at": {"$exists": False}},
                    {"availability.surface_refresh_started_at": {"$lt": now - timedelta(minutes=15)}},
                ],
            }, {"$set": {"availability.surface_refresh_started_at": now}})
            return result.modified_count > 0
        result = await get_db().dsh_plugin_installations.update_one(
            {
                "_id": row["_id"], "engine": "dsh", "enabled": True,
                "version": row["version"], "spec": row["spec"],
                "$or": [
                    {"availability.target_dsh_version": {"$ne": dsh_version}},
                    {"availability.revalidation_started_at": {"$lt": now - timedelta(minutes=15)}},
                    {"availability.status": "failed", "updated_at": {"$lt": now - timedelta(minutes=5)}},
                    {"availability.revalidation_started_at": {"$exists": False}},
                ],
            },
            {"$set": {
                "availability.status": "unverified",
                "availability.reason": "revalidation_in_progress",
                "availability.target_dsh_version": dsh_version,
                "availability.revalidation_started_at": now,
                "availability.checks.invocation": False,
                "updated_at": now,
            }},
        )
        return result.modified_count > 0

    async def ensure_indexes(self) -> None:
        await get_db().dsh_plugin_installations.create_index(
            [("main_id", 1), ("owner_user_id", 1), ("engine", 1), ("name", 1)],
            unique=True,
        )

    async def list(self, main_id: str, user_id: str = "") -> list[dict[str, Any]]:
        owner_filter = {"$in": ["", user_id]} if user_id else ""
        rows = await get_db().dsh_plugin_installations.find({
            "main_id": main_id, "owner_user_id": owner_filter, "engine": "dsh",
        }).sort([("owner_user_id", 1), ("name", 1)]).to_list(length=None)
        return [_public(row) for row in rows]

    async def save(
        self, *, main_id: str, user_id: str, name: str, version: str,
        spec: str, description: str, tool_names: list[str],
        availability: dict[str, Any] | None = None,
        archive_id: str = "", archive_digest: str = "", registry: str = "",
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        key = {"main_id": main_id, "owner_user_id": user_id, "engine": "dsh", "name": name}
        await get_db().dsh_plugin_installations.update_one(key, {
            "$set": {
                "version": version, "spec": spec, "registry": registry, "description": description,
                "tool_names": tool_names,
                "availability": availability or {"status": "unverified", "reason": "not_assessed", "checks": {}},
                "archive_id": archive_id, "archive_digest": archive_digest,
                "enabled": False, "source": "upload" if archive_id else "manual", "updated_at": now,
            },
            "$setOnInsert": {**key, "created_at": now},
        }, upsert=True)
        row = await get_db().dsh_plugin_installations.find_one(key)
        return _public(row)

    async def update_assessment(
        self, *, main_id: str, user_id: str, plugin_id: str,
        availability: dict[str, Any], tool_names: list[str], registry: str = "",
        expected_version: str = "", expected_spec: str = "",
        expected_pending_target: str = "",
        expected_surface_refresh: bool = False,
    ) -> dict[str, Any] | None:
        if not ObjectId.is_valid(plugin_id):
            return None
        current = await self.get(main_id=main_id, user_id=user_id, plugin_id=plugin_id)
        if current is None:
            return None
        previous = current.get("availability") or {}
        if (
            availability.get("status") == "session_exposed"
            and previous.get("dsh_version") == availability.get("dsh_version")
            and previous.get("checks", {}).get("invocation")
            and set(previous.get("discovered_tools") or []) == set(tool_names)
        ):
            availability = {
                **availability,
                "status": "verified",
                "reason": "invocation_verified",
                "checks": {**availability.get("checks", {}), "invocation": True},
                "last_invocation": previous.get("last_invocation"),
            }
        query = {"_id": ObjectId(plugin_id), "main_id": main_id, "owner_user_id": user_id, "engine": "dsh"}
        if expected_version:
            query["version"] = expected_version
        if expected_spec:
            query["spec"] = expected_spec
        if expected_surface_refresh:
            query["availability.status"] = {"$in": ["session_exposed", "runtime_active", "verified"]}
            query["availability.dsh_version"] = expected_pending_target
            query["availability.surface_refresh_started_at"] = {"$exists": True}
        elif expected_pending_target:
            query["availability.status"] = "unverified"
            query["availability.target_dsh_version"] = expected_pending_target
        row = await get_db().dsh_plugin_installations.find_one_and_update(
            query,
            {"$set": {"availability": availability, "tool_names": tool_names, "registry": registry, "updated_at": datetime.now(timezone.utc)}},
            return_document=True,
        )
        return _public(row) if row else None

    async def mark_invoked(
        self, *, main_id: str, user_id: str, name: str,
        version: str, spec: str, tool_name: str,
    ) -> None:
        if not all((main_id, name, version, spec, tool_name)):
            return
        await get_db().dsh_plugin_installations.update_one(
            {
                "main_id": main_id, "owner_user_id": user_id, "engine": "dsh",
                "name": name, "version": version, "spec": spec,
                "enabled": True, "tool_names": tool_name,
                "availability.status": {"$in": ["session_exposed", "verified"]},
            },
            {"$set": {
                "availability.status": "verified",
                "availability.reason": "invocation_verified",
                "availability.checks.invocation": True,
                "availability.last_invocation": {
                    "tool": tool_name, "at": datetime.now(timezone.utc).isoformat(),
                },
                "updated_at": datetime.now(timezone.utc),
            }},
        )

    async def get(self, *, main_id: str, user_id: str, plugin_id: str) -> dict[str, Any] | None:
        if not ObjectId.is_valid(plugin_id):
            return None
        return await get_db().dsh_plugin_installations.find_one({
            "_id": ObjectId(plugin_id), "main_id": main_id, "owner_user_id": user_id, "engine": "dsh",
        })

    async def set_enabled(self, *, main_id: str, user_id: str, plugin_id: str, enabled: bool) -> dict[str, Any] | None:
        if not ObjectId.is_valid(plugin_id):
            return None
        row = await get_db().dsh_plugin_installations.find_one_and_update(
            {"_id": ObjectId(plugin_id), "main_id": main_id, "owner_user_id": user_id, "engine": "dsh"},
            {"$set": {"enabled": enabled, "updated_at": datetime.now(timezone.utc)}},
            return_document=True,
        )
        return _public(row) if row else None

    async def remove(self, *, main_id: str, user_id: str, plugin_id: str) -> bool:
        if not ObjectId.is_valid(plugin_id):
            return False
        result = await get_db().dsh_plugin_installations.delete_one({
            "_id": ObjectId(plugin_id), "main_id": main_id,
            "owner_user_id": user_id, "engine": "dsh",
        })
        return result.deleted_count > 0
