"""Publication, rollback and disable semantics for immutable Runtime Profiles."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from app.core.db import get_db
from pymongo.errors import DuplicateKeyError

from .models import RuntimeProfileSnapshot


PROFILE_COLLECTION = "runtime_profile_versions"
PROFILE_AUDIT_COLLECTION = "runtime_profile_audit"


class RuntimeProfileStore(Protocol):
    async def publish(
        self,
        snapshot: RuntimeProfileSnapshot,
        *,
        actor_id: str,
        activate: bool = True,
    ) -> None: ...
    async def active(self, tenant_id: str) -> RuntimeProfileSnapshot: ...
    async def get(self, profile_version: str) -> RuntimeProfileSnapshot: ...
    async def disable(self, profile_version: str, *, actor_id: str) -> None: ...
    async def rollback(self, tenant_id: str, profile_version: str, *, actor_id: str) -> RuntimeProfileSnapshot: ...


class InMemoryRuntimeProfileStore:
    def __init__(self) -> None:
        self.snapshots: dict[str, RuntimeProfileSnapshot] = {}
        self.statuses: dict[str, str] = {}
        self.active_versions: dict[str, str] = {}
        self.audit: list[dict[str, str]] = []

    async def publish(
        self,
        snapshot: RuntimeProfileSnapshot,
        *,
        actor_id: str,
        activate: bool = True,
    ) -> None:
        existing = self.snapshots.get(snapshot.profile_version)
        if existing is not None and existing != snapshot:
            raise ValueError("profile version is immutable")
        self.snapshots[snapshot.profile_version] = snapshot
        self.statuses[snapshot.profile_version] = "published"
        if activate:
            self.active_versions[snapshot.tenant_id] = snapshot.profile_version
        self.audit.append({"action": "publish", "version": snapshot.profile_version, "actor": actor_id})

    async def active(self, tenant_id: str) -> RuntimeProfileSnapshot:
        version = self.active_versions.get(tenant_id)
        if version is None:
            raise ValueError("tenant has no published Runtime Profile")
        return await self.get(version)

    async def get(self, profile_version: str) -> RuntimeProfileSnapshot:
        snapshot = self.snapshots.get(profile_version)
        if snapshot is None:
            raise ValueError("Runtime Profile does not exist")
        if self.statuses.get(profile_version) == "disabled":
            raise ValueError("Runtime Profile is disabled")
        return snapshot

    async def disable(self, profile_version: str, *, actor_id: str) -> None:
        snapshot = self.snapshots.get(profile_version)
        if snapshot is None:
            raise ValueError("Runtime Profile does not exist")
        self.statuses[profile_version] = "disabled"
        if self.active_versions.get(snapshot.tenant_id) == profile_version:
            self.active_versions.pop(snapshot.tenant_id)
        self.audit.append({"action": "disable", "version": profile_version, "actor": actor_id})

    async def rollback(self, tenant_id: str, profile_version: str, *, actor_id: str) -> RuntimeProfileSnapshot:
        snapshot = await self.get(profile_version)
        if snapshot.tenant_id != tenant_id:
            raise ValueError("cross-tenant profile rollback is forbidden")
        self.active_versions[tenant_id] = profile_version
        self.audit.append({"action": "rollback", "version": profile_version, "actor": actor_id})
        return snapshot


class MongoRuntimeProfileStore:
    async def ensure_indexes(self) -> None:
        db = get_db()
        await db[PROFILE_COLLECTION].create_index("profile_version", unique=True)
        await db[PROFILE_COLLECTION].create_index([("tenant_id", 1), ("active", 1)])
        await db[PROFILE_COLLECTION].create_index(
            "tenant_id",
            unique=True,
            partialFilterExpression={"active": True},
            name="one_active_runtime_profile_per_tenant",
        )
        await db[PROFILE_AUDIT_COLLECTION].create_index([("tenant_id", 1), ("occurred_at", -1)])

    async def publish(
        self,
        snapshot: RuntimeProfileSnapshot,
        *,
        actor_id: str,
        activate: bool = True,
    ) -> None:
        db = get_db()
        existing = await db[PROFILE_COLLECTION].find_one({"profile_version": snapshot.profile_version})
        document = snapshot.model_dump(mode="json")
        if existing is not None:
            previous = {key: existing.get(key) for key in document}
            if previous != document:
                raise ValueError("profile version is immutable")
        else:
            try:
                await db[PROFILE_COLLECTION].insert_one(
                    {**document, "status": "published", "active": False, "published_at": self._now()}
                )
            except DuplicateKeyError:
                concurrent = await db[PROFILE_COLLECTION].find_one(
                    {"profile_version": snapshot.profile_version}
                )
                previous = {key: (concurrent or {}).get(key) for key in document}
                if previous != document:
                    raise ValueError("profile version is immutable")
        if activate:
            await db[PROFILE_COLLECTION].update_many(
                {"tenant_id": snapshot.tenant_id, "active": True}, {"$set": {"active": False}}
            )
        publish_values: dict[str, Any] = {"status": "published"}
        if activate:
            publish_values["active"] = True
        await db[PROFILE_COLLECTION].update_one(
            {"profile_version": snapshot.profile_version},
            {"$set": publish_values},
        )
        await self._audit(snapshot.tenant_id, snapshot.profile_version, "publish", actor_id)

    async def active(self, tenant_id: str) -> RuntimeProfileSnapshot:
        row = await get_db()[PROFILE_COLLECTION].find_one(
            {"tenant_id": tenant_id, "active": True, "status": "published"}
        )
        return self._snapshot(row)

    async def get(self, profile_version: str) -> RuntimeProfileSnapshot:
        row = await get_db()[PROFILE_COLLECTION].find_one(
            {"profile_version": profile_version, "status": "published"}
        )
        return self._snapshot(row)

    async def disable(self, profile_version: str, *, actor_id: str) -> None:
        db = get_db()
        row = await db[PROFILE_COLLECTION].find_one({"profile_version": profile_version})
        if row is None:
            raise ValueError("Runtime Profile does not exist")
        await db[PROFILE_COLLECTION].update_one(
            {"profile_version": profile_version}, {"$set": {"status": "disabled", "active": False}}
        )
        await self._audit(str(row["tenant_id"]), profile_version, "disable", actor_id)

    async def rollback(self, tenant_id: str, profile_version: str, *, actor_id: str) -> RuntimeProfileSnapshot:
        snapshot = await self.get(profile_version)
        if snapshot.tenant_id != tenant_id:
            raise ValueError("cross-tenant profile rollback is forbidden")
        db = get_db()
        await db[PROFILE_COLLECTION].update_many({"tenant_id": tenant_id}, {"$set": {"active": False}})
        await db[PROFILE_COLLECTION].update_one(
            {"profile_version": profile_version}, {"$set": {"active": True}}
        )
        await self._audit(tenant_id, profile_version, "rollback", actor_id)
        return snapshot

    async def _audit(self, tenant_id: str, profile_version: str, action: str, actor_id: str) -> None:
        await get_db()[PROFILE_AUDIT_COLLECTION].insert_one(
            {
                "tenant_id": tenant_id,
                "profile_version": profile_version,
                "action": action,
                "actor_id": actor_id,
                "occurred_at": self._now(),
            }
        )

    @staticmethod
    def _snapshot(row: dict[str, Any] | None) -> RuntimeProfileSnapshot:
        if row is None:
            raise ValueError("published Runtime Profile does not exist")
        snapshot = {
            field_name: row[field_name]
            for field_name in RuntimeProfileSnapshot.model_fields
            if field_name in row
        }
        return RuntimeProfileSnapshot.model_validate(snapshot)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)
