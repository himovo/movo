from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.db import get_db
from app.core.tenant import resolve_main_id

from .schedule import next_run_at, utc_now
from .time_contract import SCHEDULE_VERSION, format_wall_datetime, job_wall_time, submitted_wall_time


JOBS = "scheduled_jobs"
RUNS = "scheduled_job_runs"


def _format_datetime(dt: Any) -> str | None:
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(dt, str) and dt:
        return dt
    return None


def serialize_job(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(doc.get("_id") or ""),
        "main_id": resolve_main_id(doc.get("main_id")),
        "owner_user_id": str(doc.get("owner_user_id") or ""),
        "run_as_user_id": str(doc.get("run_as_user_id") or ""),
        "name": str(doc.get("name") or ""),
        "prompt": str(doc.get("prompt") or ""),
        "schedule_kind": str(doc.get("schedule_kind") or "daily"),
        "timezone": str(doc.get("timezone") or "UTC"),
        "run_at": format_wall_datetime(job_wall_time(doc)),
        "weekdays": list(doc.get("weekdays") or []),
        "session_mode": str(doc.get("session_mode") or "fixed"),
        "session_id": str(doc.get("session_id") or "") or None,
        "session_title_template": str(doc.get("session_title_template") or "{name} · {date}"),
        "enabled": bool(doc.get("enabled")),
        "output_spec": dict(doc.get("output_spec") or {}),
        "next_run_at": _format_datetime(doc.get("next_run_at")),
        "last_run_at": _format_datetime(doc.get("last_run_at")),
        "last_run_status": str(doc.get("last_run_status") or ""),
        "last_session_id": str(doc.get("last_session_id") or "") or None,
        "created_at": _format_datetime(doc.get("created_at")),
        "updated_at": _format_datetime(doc.get("updated_at")),
    }


class ScheduledTaskRepository:
    async def ensure_indexes(self) -> None:
        db = get_db()
        await db[JOBS].create_index(
            [("main_id", 1), ("owner_user_id", 1), ("enabled", 1), ("next_run_at", 1)],
            name="scheduled_jobs_owner_due",
        )
        await db[JOBS].create_index([("enabled", 1), ("next_run_at", 1)], name="scheduled_jobs_due")
        await db[RUNS].create_index(
            [("job_id", 1), ("scheduled_for", 1)], unique=True, name="scheduled_runs_idempotency"
        )
        await db[RUNS].create_index(
            [("main_id", 1), ("owner_user_id", 1), ("created_at", -1)], name="scheduled_runs_owner"
        )

    async def list_jobs(self, *, main_id: str, user_id: str) -> List[Dict[str, Any]]:
        cursor = get_db()[JOBS].find(
            {"main_id": resolve_main_id(main_id), "owner_user_id": str(user_id)}
        ).sort([("created_at", -1)])
        return [serialize_job(row) async for row in cursor]

    async def get_job(self, job_id: str, *, main_id: str, user_id: str) -> Dict[str, Any] | None:
        if not ObjectId.is_valid(job_id):
            return None
        return await get_db()[JOBS].find_one(
            {"_id": ObjectId(job_id), "main_id": resolve_main_id(main_id), "owner_user_id": str(user_id)}
        )

    async def create_job(self, payload: Dict[str, Any], *, main_id: str, user_id: str) -> Dict[str, Any]:
        now = utc_now()
        timezone_name = str(payload.get("timezone") or "UTC")
        doc = {
            **dict(payload),
            "run_at": submitted_wall_time(payload["run_at"], timezone_name),
            "schedule_version": SCHEDULE_VERSION,
            "main_id": resolve_main_id(main_id),
            "owner_user_id": str(user_id),
            "run_as_user_id": str(user_id),
            "created_by": str(user_id),
            "created_at": now,
            "updated_at": now,
            "last_run_status": "",
        }
        doc["next_run_at"] = next_run_at(
            schedule_kind=doc["schedule_kind"],
            run_at=job_wall_time(doc),
            timezone_name=doc["timezone"],
            weekdays=doc.get("weekdays"),
            after_utc=now - timedelta(seconds=1),
        ) if doc.get("enabled") else None
        if doc.get("enabled") and doc["next_run_at"] is None:
            raise ValueError("单次任务的执行时间不能早于当前时间")
        result = await get_db()[JOBS].insert_one(doc)
        doc["_id"] = result.inserted_id
        return serialize_job(doc)

    async def update_job(
        self, job_id: str, updates: Dict[str, Any], *, main_id: str, user_id: str
    ) -> Dict[str, Any] | None:
        current = await self.get_job(job_id, main_id=main_id, user_id=user_id)
        if not current:
            return None
        schedule_fields = {"schedule_kind", "timezone", "run_at", "weekdays", "enabled"}
        schedule_changed = bool(schedule_fields.intersection(updates))
        previous_wall_time = job_wall_time(current)
        merged = {**current, **updates}
        timezone_name = str(merged.get("timezone") or "UTC")
        wall_time = submitted_wall_time(updates["run_at"], timezone_name) if "run_at" in updates else previous_wall_time
        updates["run_at"] = wall_time
        updates["schedule_version"] = SCHEDULE_VERSION
        merged["run_at"] = wall_time
        merged["schedule_version"] = SCHEDULE_VERSION
        enabled = bool(merged.get("enabled"))
        if schedule_changed:
            updates["next_run_at"] = next_run_at(
                schedule_kind=str(merged.get("schedule_kind") or "daily"),
                run_at=wall_time,
                timezone_name=timezone_name,
                weekdays=list(merged.get("weekdays") or []),
                after_utc=utc_now() - timedelta(seconds=1),
            ) if enabled else None
            if enabled and updates["next_run_at"] is None:
                raise ValueError("单次任务的执行时间不能早于当前时间")
        updates["updated_at"] = utc_now()
        doc = await get_db()[JOBS].find_one_and_update(
            {"_id": current["_id"], "main_id": resolve_main_id(main_id), "owner_user_id": str(user_id)},
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )
        return serialize_job(doc) if doc else None

    async def delete_job(self, job_id: str, *, main_id: str, user_id: str) -> bool:
        if not ObjectId.is_valid(job_id):
            return False
        result = await get_db()[JOBS].delete_one(
            {"_id": ObjectId(job_id), "main_id": resolve_main_id(main_id), "owner_user_id": str(user_id)}
        )
        return bool(result.deleted_count)

    async def claim_due_job(self, *, worker_id: str) -> Dict[str, Any] | None:
        now = utc_now()
        job = await get_db()[JOBS].find_one_and_update(
            {"enabled": True, "next_run_at": {"$ne": None, "$lte": now}, "$or": [
                {"lease_until": {"$exists": False}}, {"lease_until": None}, {"lease_until": {"$lt": now}}
            ]},
            {"$set": {"lease_owner": worker_id, "lease_until": now + timedelta(minutes=2)}},
            sort=[("next_run_at", 1)],
            return_document=ReturnDocument.AFTER,
        )
        return job

    async def create_run(self, job: Dict[str, Any], *, scheduled_for: datetime, manual: bool = False) -> Dict[str, Any] | None:
        now = utc_now()
        run_doc = {
            "run_id": uuid.uuid4().hex,
            "job_id": str(job["_id"]),
            "main_id": resolve_main_id(job.get("main_id")),
            "owner_user_id": str(job.get("owner_user_id") or ""),
            "run_as_user_id": str(job.get("run_as_user_id") or ""),
            "scheduled_for": scheduled_for,
            "manual": manual,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
        }
        try:
            await get_db()[RUNS].insert_one(run_doc)
        except DuplicateKeyError:
            return None
        return run_doc

    async def get_run(self, job: Dict[str, Any], *, scheduled_for: datetime) -> Dict[str, Any] | None:
        return await get_db()[RUNS].find_one({"job_id": str(job["_id"]), "scheduled_for": scheduled_for})

    async def claim_pending_run(self, *, worker_id: str, run_id: str | None = None) -> Dict[str, Any] | None:
        now = utc_now()
        query: Dict[str, Any] = {
            "status": {"$in": ["queued", "dispatching"]},
            "$or": [
                {"dispatch_lease_until": {"$exists": False}},
                {"dispatch_lease_until": None},
                {"dispatch_lease_until": {"$lt": now}},
            ],
        }
        if run_id:
            query["run_id"] = run_id
        return await get_db()[RUNS].find_one_and_update(
            query,
            {"$set": {
                "status": "dispatching",
                "dispatch_owner": worker_id,
                "dispatch_lease_until": now + timedelta(minutes=2),
                "updated_at": now,
            }},
            sort=[("created_at", 1)],
            return_document=ReturnDocument.AFTER,
        )

    async def get_job_for_run(self, run: Dict[str, Any]) -> Dict[str, Any] | None:
        job_id = str(run.get("job_id") or "")
        return await get_db()[JOBS].find_one({"_id": ObjectId(job_id)}) if ObjectId.is_valid(job_id) else None

    async def fail_pending_run(self, run: Dict[str, Any], error: str) -> None:
        now = utc_now()
        await get_db()[RUNS].update_one(
            {"run_id": str(run.get("run_id") or ""), "status": "dispatching"},
            {"$set": {"status": "failed", "error": error[:1000], "finished_at": now, "updated_at": now}},
        )

    async def release_after_dispatch(self, job: Dict[str, Any], *, scheduled_for: datetime) -> None:
        now = utc_now()
        next_at = next_run_at(
            schedule_kind=str(job.get("schedule_kind") or "daily"),
            run_at=job_wall_time(job),
            timezone_name=str(job.get("timezone") or "UTC"),
            weekdays=list(job.get("weekdays") or []),
            # A recurring task catches up at most once after downtime.
            after_utc=max(scheduled_for, now),
        )
        result = await get_db()[JOBS].update_one(
            {"_id": job["_id"], "next_run_at": {"$lte": scheduled_for}},
            {"$set": {
                "next_run_at": next_at,
                "enabled": bool(next_at) and bool(job.get("enabled")),
                "last_run_at": scheduled_for,
                "lease_owner": None,
                "lease_until": None,
                "updated_at": now,
            }},
        )
        if not result.modified_count:
            # A concurrent user edit owns the new schedule; only release this worker's lease.
            await get_db()[JOBS].update_one(
                {"_id": job["_id"], "lease_owner": job.get("lease_owner")},
                {"$set": {"lease_owner": None, "lease_until": None, "last_run_at": scheduled_for}},
            )


scheduled_task_repository = ScheduledTaskRepository()
