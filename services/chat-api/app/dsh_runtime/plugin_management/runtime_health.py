"""Persist native Runtime activation failures for installed plugins."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from bson import ObjectId

from app.core.db import get_db


logger = logging.getLogger(__name__)


async def mark_runtime_unavailable(
    *, tenant_id: str, requested: list[dict], activated: list[dict], reason: str,
) -> None:
    active_ids = {str(plugin.get("installation_id") or "") for plugin in activated}
    for plugin in requested:
        installation_id = str(plugin.get("installation_id") or "")
        if installation_id in active_ids or not ObjectId.is_valid(installation_id):
            continue
        try:
            await get_db().dsh_plugin_installations.update_one(
                {
                    "_id": ObjectId(installation_id),
                    "main_id": tenant_id,
                    "engine": "dsh",
                    "version": str(plugin.get("version") or ""),
                    "enabled": True,
                },
                {"$set": {
                    "availability.status": "failed",
                    "availability.reason": reason[:2000],
                    "availability.error_code": "runtime_activation_failed",
                    "availability.checks.runtime": False,
                    "updated_at": datetime.now(timezone.utc),
                }},
            )
        except Exception:
            logger.exception("Could not record plugin Runtime activation failure", extra={
                "tenant_id": tenant_id, "installation_id": installation_id,
            })
