"""Make the owner's persisted DSH sessions visible to a plugin's current profile."""

from __future__ import annotations

import logging
from urllib.parse import quote

from app.core.db import get_db


logger = logging.getLogger(__name__)
_BATCH_SIZE = 100


async def hydrate_owned_history(*, http, host_url: str, headers: dict[str, str],
                                tenant_id: str, user_id: str,
                                target_profile_version: str, runtime_id: str) -> None:
    db = get_db()
    ids: list[str] = []
    async for conversation in db.chat_sessions.find(
        {"main_id": tenant_id, "user_id": user_id}, {"_id": 1},
    ):
        ids.append(str(conversation["_id"]))
        if len(ids) == _BATCH_SIZE:
            await _hydrate_batch(db, http, host_url, headers, tenant_id,
                                 target_profile_version, runtime_id, ids)
            ids.clear()
    if ids:
        await _hydrate_batch(db, http, host_url, headers, tenant_id,
                             target_profile_version, runtime_id, ids)


async def _hydrate_batch(db, http, host_url: str, headers: dict[str, str],
                         tenant_id: str, target_profile_version: str,
                         runtime_id: str, conversation_ids: list[str]) -> None:
    sessions = []
    async for binding in db.agent_kernel_bindings.find({
        "tenant_id": tenant_id,
        "conversation_id": {"$in": conversation_ids},
        "current": True,
        "execution_location": "server",
    }, {"profile_version": 1, "kernel_session_id": 1}):
        sessions.append({
            "profileVersion": binding["profile_version"],
            "sessionId": binding["kernel_session_id"],
        })
    if not sessions:
        return
    response = await http.post(
        f"{host_url}/v1/runtimes/{quote(runtime_id, safe='')}/plugin-history/hydrate", headers=headers,
                               json={"tenantId": tenant_id,
                                     "targetProfileVersion": target_profile_version,
                                     "sessions": sessions})
    response.raise_for_status()
    result = response.json()
    if result.get("unavailable"):
        logger.warning("Plugin history sessions unavailable: tenant=%s count=%s",
                       tenant_id, result["unavailable"])
    if result.get("resumeFailures"):
        logger.warning("Plugin history sessions failed to resume: tenant=%s count=%s",
                       tenant_id, result["resumeFailures"])
