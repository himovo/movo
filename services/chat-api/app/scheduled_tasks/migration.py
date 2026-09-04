from __future__ import annotations

from datetime import datetime, timedelta

from app.core.db import get_db

from .schedule import UTC, next_run_at, utc_now
from .time_contract import SCHEDULE_VERSION, job_wall_time


async def migrate_legacy_schedules() -> None:
    """Convert legacy UTC anchors to explicit wall times before dispatching them."""
    db = get_db()
    now = utc_now()
    cursor = db.scheduled_jobs.find({"schedule_version": {"$ne": SCHEDULE_VERSION}})
    async for job in cursor:
        try:
            wall_time = job_wall_time(job)
            current_next = job.get("next_run_at")
            comparable_next = (
                current_next.astimezone(UTC).replace(tzinfo=None)
                if isinstance(current_next, datetime) and current_next.tzinfo is not None
                else current_next
            )
            overdue = isinstance(comparable_next, datetime) and comparable_next <= now
            next_at = current_next if overdue else (
                next_run_at(
                    schedule_kind=str(job.get("schedule_kind") or "daily"),
                    run_at=wall_time,
                    timezone_name=str(job.get("timezone") or "UTC"),
                    weekdays=list(job.get("weekdays") or []),
                    after_utc=now - timedelta(seconds=1),
                ) if job.get("enabled") else None
            )
            await db.scheduled_jobs.update_one(
                {"_id": job["_id"], "schedule_version": {"$ne": SCHEDULE_VERSION}},
                {"$set": {
                    "run_at": wall_time,
                    "schedule_version": SCHEDULE_VERSION,
                    "next_run_at": next_at,
                    "enabled": bool(job.get("enabled")) and (next_at is not None),
                    "updated_at": now,
                }},
            )
        except (KeyError, TypeError, ValueError):
            # Leave malformed legacy rows untouched and visible for manual repair.
            continue
