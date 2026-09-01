from __future__ import annotations

from datetime import timedelta
from typing import Any

from pymongo import ReturnDocument

from app.core.db import get_db

from .contracts import PresentationJobClaim, PresentationJobSnapshot, utc_now
from .identity import PresentationJobIdentity


class PresentationJobRepository:
    """Mongo-backed checkpoints shared by Community and commercial editions."""

    COLLECTION = "presentation_generation_jobs"
    LEASE_MINUTES = 15

    async def ensure_indexes(self) -> None:
        collection = get_db()[self.COLLECTION]
        await collection.create_index("job_id", unique=True)
        await collection.create_index("business_key", unique=True)
        await collection.create_index("continuation_token", unique=True)
        await collection.create_index(
            [("tenant_id", 1), ("user_id", 1), ("conversation_id", 1), ("updated_at", -1)]
        )

    async def recover_running(self) -> int:
        """A restarted API process has no surviving in-process page workers."""

        now = utc_now()
        result = await get_db()[self.COLLECTION].update_many(
            {
                "status": "running",
                "$or": [
                    {"lease_expires_at": {"$lt": now}},
                    {"lease_expires_at": {"$exists": False}},
                ],
            },
            {"$set": {
                "status": "interrupted",
                "stage": "interrupted",
                "error": "presentation worker restarted",
                "updated_at": now,
            }},
        )
        return int(result.modified_count)

    async def claim(
        self,
        *,
        identity: PresentationJobIdentity,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        message_id: str,
        generation_mode: str,
        action_id: str,
    ) -> PresentationJobClaim:
        collection = get_db()[self.COLLECTION]
        now = utc_now()
        await collection.update_one(
            {"business_key": identity.business_key},
            {"$setOnInsert": {
                "job_id": identity.job_id,
                "business_key": identity.business_key,
                "continuation_token": identity.continuation_token,
                "request_fingerprint": identity.request_fingerprint,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "conversation_id": conversation_id,
                "message_id": message_id,
                "generation_mode": generation_mode,
                "owner_action_id": "",
                "status": "pending",
                "stage": "pending",
                "story_plan": {},
                "planning": {},
                "pages": {},
                "final_result": {},
                "error": "",
                "lease_expires_at": self._lease_deadline(now),
                "created_at": now,
                "updated_at": now,
            }},
            upsert=True,
        )
        row = await collection.find_one_and_update(
            {
                "business_key": identity.business_key,
                "$or": [
                    {"status": {"$in": ["pending", "interrupted", "failed"]}},
                    {"status": "running", "lease_expires_at": {"$lt": now}},
                ],
            },
            {"$set": {
                "status": "running",
                "stage": "resuming" if await self._has_progress(identity.business_key) else "starting",
                "owner_action_id": action_id,
                "error": "",
                "lease_expires_at": self._lease_deadline(),
                "updated_at": utc_now(),
            }},
            return_document=ReturnDocument.AFTER,
        )
        if row is not None:
            return PresentationJobClaim(snapshot=self._snapshot(row), acquired=True)
        current = await collection.find_one({"business_key": identity.business_key})
        if current is None:
            raise LookupError("presentation job disappeared while being claimed")
        snapshot = self._snapshot(current)
        return PresentationJobClaim(
            snapshot=snapshot,
            acquired=snapshot.status == "running" and snapshot.owner_action_id == action_id,
        )

    async def get(self, job_id: str) -> PresentationJobSnapshot | None:
        row = await get_db()[self.COLLECTION].find_one({"job_id": job_id})
        return self._snapshot(row) if row else None

    async def save_stage(self, job_id: str, action_id: str, stage: str) -> None:
        await self._owned_update(job_id, action_id, {"stage": stage})

    async def save_story_plan(self, job_id: str, action_id: str, payload: dict[str, Any]) -> None:
        await self._owned_update(job_id, action_id, {"story_plan": dict(payload), "stage": "story_ready"})

    async def save_planning(self, job_id: str, action_id: str, payload: dict[str, Any]) -> None:
        await self._owned_update(job_id, action_id, {"planning": dict(payload), "stage": "planning_ready"})

    async def save_page(self, job_id: str, action_id: str, page_id: str, payload: dict[str, Any]) -> None:
        safe_page_id = str(page_id or "").strip().replace(".", "_")
        if not safe_page_id:
            raise ValueError("presentation checkpoint page_id is empty")
        await self._owned_update(
            job_id,
            action_id,
            {f"pages.{safe_page_id}": dict(payload), "stage": "page_generation"},
        )

    async def complete(self, job_id: str, action_id: str, result: dict[str, Any]) -> PresentationJobSnapshot:
        row = await get_db()[self.COLLECTION].find_one_and_update(
            {"job_id": job_id, "owner_action_id": action_id, "status": "running"},
            {"$set": {
                "status": "succeeded",
                "stage": "completed",
                "final_result": dict(result),
                "error": "",
                "updated_at": utc_now(),
            }},
            return_document=ReturnDocument.AFTER,
        )
        if row is None:
            raise RuntimeError("presentation job ownership changed before completion")
        return self._snapshot(row)

    async def interrupt(self, job_id: str, action_id: str, reason: str) -> None:
        await get_db()[self.COLLECTION].update_one(
            {"job_id": job_id, "owner_action_id": action_id, "status": "running"},
            {"$set": {
                "status": "interrupted",
                "stage": "interrupted",
                "error": str(reason or "presentation generation interrupted")[:2000],
                "updated_at": utc_now(),
            }},
        )

    async def fail(self, job_id: str, action_id: str, reason: str) -> None:
        await get_db()[self.COLLECTION].update_one(
            {"job_id": job_id, "owner_action_id": action_id, "status": "running"},
            {"$set": {
                "status": "failed",
                "stage": "failed",
                "error": str(reason or "presentation generation failed")[:2000],
                "updated_at": utc_now(),
            }},
        )

    async def cancel_by_action(self, action_id: str, reason: str = "user_cancelled") -> int:
        result = await get_db()[self.COLLECTION].update_many(
            {"owner_action_id": action_id, "status": {"$in": ["pending", "running", "interrupted"]}},
            {"$set": {"status": "cancelled", "stage": "cancelled", "error": reason, "updated_at": utc_now()}},
        )
        return int(result.modified_count)

    async def cancel_conversation(self, tenant_id: str, user_id: str, conversation_id: str) -> int:
        result = await get_db()[self.COLLECTION].update_many(
            {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "conversation_id": conversation_id,
                "status": {"$in": ["pending", "running"]},
            },
            {"$set": {
                "status": "cancelled",
                "stage": "cancelled",
                "error": "user_cancelled",
                "updated_at": utc_now(),
            }},
        )
        return int(result.modified_count)

    async def continuation_for_action(self, action_id: str) -> dict[str, Any]:
        row = await get_db()[self.COLLECTION].find_one({"owner_action_id": action_id})
        if not row:
            return {}
        snapshot = self._snapshot(row)
        return {
            "job_id": snapshot.job_id,
            "continuation_token": snapshot.continuation_token,
            "status": snapshot.status,
            "stage": snapshot.stage,
            "completed_page_count": len(snapshot.pages),
            "retry_allowed": False,
            "resume_supported": True,
        }

    async def _owned_update(self, job_id: str, action_id: str, fields: dict[str, Any]) -> None:
        result = await get_db()[self.COLLECTION].update_one(
            {"job_id": job_id, "owner_action_id": action_id, "status": "running"},
            {"$set": {
                **fields,
                "lease_expires_at": self._lease_deadline(),
                "updated_at": utc_now(),
            }},
        )
        if result.matched_count != 1:
            raise RuntimeError("presentation job is no longer owned by this action")

    async def _has_progress(self, business_key: str) -> bool:
        row = await get_db()[self.COLLECTION].find_one(
            {"business_key": business_key},
            {"story_plan": 1, "planning": 1, "pages": 1},
        )
        return bool(row and (row.get("story_plan") or row.get("planning") or row.get("pages")))

    @classmethod
    def _lease_deadline(cls, now=None):
        return (now or utc_now()) + timedelta(minutes=cls.LEASE_MINUTES)

    @staticmethod
    def _snapshot(row: dict[str, Any]) -> PresentationJobSnapshot:
        cleaned = dict(row)
        cleaned.pop("_id", None)
        return PresentationJobSnapshot.model_validate(cleaned)


__all__ = ["PresentationJobRepository"]
