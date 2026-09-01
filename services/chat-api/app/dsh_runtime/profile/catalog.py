"""Read-only model catalog boundary over ASKAI admin collections."""

from __future__ import annotations

from typing import Any, Protocol

from bson import ObjectId
from bson.errors import InvalidId

from app.core.db import get_db
from app.llm.configured_models import INSTANCE_COLLECTION, PROVIDER_COLLECTION


class ModelCatalog(Protocol):
    async def resolve(self, tenant_id: str, model_instance_id: str | None) -> tuple[dict[str, Any], dict[str, Any]]: ...


class MongoModelCatalog:
    async def resolve(
        self,
        tenant_id: str,
        model_instance_id: str | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        db = get_db()
        if model_instance_id:
            try:
                identifier = ObjectId(model_instance_id)
            except InvalidId as exc:
                raise ValueError("model instance id is invalid") from exc
            instance = await db[INSTANCE_COLLECTION].find_one(
                {"_id": identifier, "main_id": tenant_id}
            )
        else:
            instance = await self._default_instance(db, tenant_id)
        if instance is None:
            raise ValueError("no active chat model is available for this tenant")
        source_tenant = str(instance.get("main_id") or "")
        if source_tenant != tenant_id:
            raise ValueError("cross-tenant model access is forbidden")
        provider = await db[PROVIDER_COLLECTION].find_one({"_id": instance.get("provider_id")})
        if provider is None:
            raise ValueError("model provider does not exist")
        return dict(instance), dict(provider)

    async def _default_instance(self, db: Any, tenant_id: str) -> dict[str, Any] | None:
        return await db[INSTANCE_COLLECTION].find_one(
            {"main_id": tenant_id, "status": "active", "capabilities": "chat"},
            sort=[("priority", 1), ("updated_at", -1)],
        )
