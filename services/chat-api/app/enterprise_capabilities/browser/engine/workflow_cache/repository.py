from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
import uuid

from app.core.db import get_db

from .contracts import (
    CachedBrowserWorkflow,
    CachedCompletionContract,
    CachedFieldBinding,
    CachedRequestTemplate,
    CachedWorkflowStep,
    WorkflowIdentity,
)
from .route_selector import replay_route_rank


CURRENT_WORKFLOW_ADMISSION_REVISION = 3


class BrowserWorkflowCacheRepository:
    # V3 is intentionally a new collection.  V2 enforced one document per
    # signature and overwrote a good workflow with every later success, which
    # made safe champion/challenger versioning impossible.
    collection_name = "browser_workflow_cache_v3"

    def __init__(self) -> None:
        self._index_lock = asyncio.Lock()
        self._indexes_ready = False

    async def find(self, identity: WorkflowIdentity) -> CachedBrowserWorkflow | None:
        await self._ensure_indexes()
        docs = await self._collection().find(
            {
                "identity.signature_hash": identity.signature_hash,
                "status": {"$in": ["candidate", "active", "degraded"]},
            },
        ).sort([("replay_success_count", -1), ("quality_score", -1), ("updated_at", -1)]).to_list(length=20)
        candidates = [
            CachedBrowserWorkflow.model_validate(doc)
            for doc in docs if isinstance(doc, dict)
        ]
        return max(candidates, key=replay_route_rank) if candidates else None

    async def find_by_id(
        self,
        workflow_id: str,
        *,
        include_quarantined: bool = False,
    ) -> CachedBrowserWorkflow | None:
        await self._ensure_indexes()
        doc = await self._collection().find_one({
            "workflow_id": str(workflow_id or ""),
            "status": {"$in": (
                ["candidate", "active", "degraded", "quarantined"]
                if include_quarantined else ["candidate", "active", "degraded"]
            )},
        })
        return CachedBrowserWorkflow.model_validate(doc) if isinstance(doc, dict) else None

    async def find_candidates(
        self,
        *,
        user_id: str,
        site_id: str,
        limit: int = 30,
    ) -> list[CachedBrowserWorkflow]:
        await self._ensure_indexes()
        cursor = self._collection().find(
            {
                "identity.user_id": str(user_id),
                "identity.site_id": str(site_id),
                "status": {"$in": ["candidate", "active", "degraded"]},
            },
        ).sort([("replay_success_count", -1), ("updated_at", -1)]).limit(max(1, min(limit, 100)))
        docs = await cursor.to_list(length=max(1, min(limit, 100)))
        return [CachedBrowserWorkflow.model_validate(doc) for doc in docs if isinstance(doc, dict)]

    async def find_user_candidates(
        self,
        *,
        user_id: str,
        limit: int = 100,
    ) -> list[CachedBrowserWorkflow]:
        """Bounded same-user fallback when planning omitted the site scope."""
        await self._ensure_indexes()
        bounded = max(1, min(limit, 100))
        docs = await self._collection().find(
            {
                "identity.user_id": str(user_id),
                "status": {"$in": ["candidate", "active", "degraded"]},
            },
        ).sort([("replay_success_count", -1), ("updated_at", -1)]).limit(bounded).to_list(length=bounded)
        return [CachedBrowserWorkflow.model_validate(doc) for doc in docs if isinstance(doc, dict)]

    async def upsert_success(
        self,
        *,
        identity: WorkflowIdentity,
        steps: list[CachedWorkflowStep],
        field_bindings: list[CachedFieldBinding],
        request_template: CachedRequestTemplate | None,
        request_fingerprint: str,
        completion: CachedCompletionContract,
        dynamic_input_roles: list[str],
        run_id: str,
        replayed: bool,
        display_name: str = "",
        plan_hash: str = "",
        quality_score: int = 0,
        matched_workflow_id: str = "",
        replay_failed: bool = False,
    ) -> CachedBrowserWorkflow:
        await self._ensure_indexes()
        now = datetime.utcnow()
        existing = await self._collection().find_one({
            "identity.signature_hash": identity.signature_hash,
            "plan_hash": str(plan_hash or ""),
        })
        if isinstance(existing, dict):
            workflow_id = str(existing.get("workflow_id") or uuid.uuid4().hex)
            replay_success = bool(replayed and not replay_failed)
            replay_success_count = int(existing.get("replay_success_count") or 0) + (1 if replay_success else 0)
            success_count = int(existing.get("success_count") or 0) + 1
            status = "active" if replay_success_count > 0 else str(existing.get("status") or "candidate")
            await self._collection().update_one(
                {"_id": existing.get("_id")},
                {"$set": {
                    "workflow_id": workflow_id,
                    "display_name": str(display_name or existing.get("display_name") or "")[:120],
                    "admission_revision": CURRENT_WORKFLOW_ADMISSION_REVISION,
                    "version": 3,
                    "identity": identity.model_dump(mode="json"),
                    "status": status,
                    "steps": [item.model_dump(mode="json") for item in steps],
                    "field_bindings": [item.model_dump(mode="json") for item in field_bindings],
                    "request_template": (
                        request_template.model_dump(mode="json") if request_template is not None else None
                    ),
                    "request_fingerprint": str(request_fingerprint or ""),
                    "plan_hash": str(plan_hash or ""),
                    "quality_score": max(int(existing.get("quality_score") or 0), int(quality_score or 0)),
                    "completion": completion.model_dump(mode="json"),
                    "dynamic_input_roles": list(dynamic_input_roles),
                    "success_count": success_count,
                    "replay_success_count": replay_success_count,
                    "consecutive_failures": 0,
                    "updated_at": now,
                }},
            )
            updated = dict(existing)
            updated.update({
                "workflow_id": workflow_id,
                "display_name": str(display_name or existing.get("display_name") or "")[:120],
                "admission_revision": CURRENT_WORKFLOW_ADMISSION_REVISION,
                "version": 3,
                "identity": identity.model_dump(mode="json"),
                "status": status,
                "steps": [item.model_dump(mode="json") for item in steps],
                "field_bindings": [item.model_dump(mode="json") for item in field_bindings],
                "request_template": (
                    request_template.model_dump(mode="json") if request_template is not None else None
                ),
                "request_fingerprint": str(request_fingerprint or ""),
                "plan_hash": str(plan_hash or ""),
                "quality_score": max(int(existing.get("quality_score") or 0), int(quality_score or 0)),
                "completion": completion.model_dump(mode="json"),
                "dynamic_input_roles": list(dynamic_input_roles),
                "success_count": success_count,
                "replay_success_count": replay_success_count,
                "consecutive_failures": 0,
                "updated_at": now,
            })
            if status == "active":
                await self._demote_other_active(identity.signature_hash, workflow_id)
            return CachedBrowserWorkflow.model_validate(updated)
        repaired = bool(replay_failed and matched_workflow_id)
        # A repaired route is a challenger, not an immediate champion.  The
        # failed predecessor is degraded so this candidate gets the next trial;
        # only a successful local replay promotes it to active.
        status = "candidate"
        created = CachedBrowserWorkflow(
            workflow_id=uuid.uuid4().hex,
            display_name=str(display_name or "")[:120],
            admission_revision=CURRENT_WORKFLOW_ADMISSION_REVISION,
            version=3,
            identity=identity,
            steps=steps,
            field_bindings=field_bindings,
            request_template=request_template,
            request_fingerprint=str(request_fingerprint or ""),
            plan_hash=str(plan_hash or ""),
            quality_score=max(0, int(quality_score or 0)),
            supersedes_workflow_id=str(matched_workflow_id or "") if repaired else "",
            completion=completion,
            dynamic_input_roles=dynamic_input_roles,
            created_from_run_id=str(run_id or ""),
            replay_success_count=0,
            status=status,
            created_at=now,
            updated_at=now,
        )
        await self._collection().insert_one(created.model_dump(mode="python"))
        if repaired:
            await self._collection().update_one(
                {"workflow_id": str(matched_workflow_id)},
                {"$set": {"status": "degraded", "updated_at": now}},
            )
        return created

    async def mark_failure(self, workflow_id: str, reason: str) -> None:
        await self._ensure_indexes()
        existing = await self._collection().find_one({"workflow_id": str(workflow_id or "")})
        if not isinstance(existing, dict):
            return
        failures = int(existing.get("failure_count") or 0) + 1
        consecutive = int(existing.get("consecutive_failures") or 0) + 1
        status = "quarantined" if consecutive >= 3 else "degraded"
        await self._collection().update_one(
            {"_id": existing.get("_id")},
            {"$set": {
                "failure_count": failures,
                "consecutive_failures": consecutive,
                "status": status,
                "last_failure_reason": str(reason or "")[:500],
                "updated_at": datetime.utcnow(),
            }},
        )

    async def quarantine(self, workflow_id: str, reason: str) -> None:
        """Immediately isolate a structurally invalid legacy workflow."""
        await self._ensure_indexes()
        await self._collection().update_one(
            {"workflow_id": str(workflow_id or "")},
            {"$set": {
                "status": "quarantined",
                "last_failure_reason": str(reason or "")[:500],
                "updated_at": datetime.utcnow(),
            }},
        )

    def _collection(self) -> Any:
        return get_db()[self.collection_name]

    async def _demote_other_active(self, signature_hash: str, workflow_id: str) -> None:
        await self._collection().update_many(
            {
                "identity.signature_hash": str(signature_hash),
                "workflow_id": {"$ne": str(workflow_id)},
                "status": "active",
            },
            {"$set": {"status": "degraded", "updated_at": datetime.utcnow()}},
        )

    async def _ensure_indexes(self) -> None:
        if self._indexes_ready:
            return
        async with self._index_lock:
            if self._indexes_ready:
                return
            collection = self._collection()
            await collection.create_index(
                [("workflow_id", 1)],
                unique=True,
                name="uq_browser_workflow_id_v3",
            )
            await collection.create_index(
                [("identity.signature_hash", 1), ("plan_hash", 1)],
                unique=True,
                name="uq_browser_workflow_plan_v3",
            )
            await collection.create_index(
                [("identity.user_id", 1), ("identity.site_id", 1), ("status", 1)],
                name="ix_browser_workflow_lookup",
            )
            self._indexes_ready = True

__all__ = ["BrowserWorkflowCacheRepository", "CURRENT_WORKFLOW_ADMISSION_REVISION"]
