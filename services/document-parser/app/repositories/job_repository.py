from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING, DESCENDING

from app.core.config import settings
from app.core.db import get_db


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _collection():
    return get_db()[settings.jobs_collection]


def ensure_job_indexes() -> None:
    collection = _collection()
    collection.create_index([("jobId", ASCENDING)], unique=True, name="job_id_unique")
    collection.create_index([("documentId", ASCENDING), ("createdAt", DESCENDING)], name="document_created")
    collection.create_index([("status", ASCENDING), ("createdAt", DESCENDING)], name="status_created")


def _serialize(job: dict[str, Any] | None) -> dict[str, Any] | None:
    if job is None:
        return None
    item = dict(job)
    item.pop("_id", None)
    for key in ("createdAt", "updatedAt", "startedAt", "finishedAt"):
        value = item.get(key)
        if isinstance(value, datetime):
            item[key] = value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        elif value is None:
            item[key] = ""
    return item


def create_job(job_id: str, job_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    now = utcnow()
    document_id = str(payload.get("documentId") or "")
    main_id = str(payload.get("mainId") or "default")
    job = {
        "jobId": job_id,
        "jobType": job_type,
        "documentId": document_id,
        "mainId": main_id,
        "status": "queued",
        "progress": 0,
        "attempts": 0,
        "payload": payload,
        "result": {},
        "error": "",
        "createdAt": now,
        "updatedAt": now,
        "startedAt": None,
        "finishedAt": None,
    }
    _collection().insert_one(job)
    return _serialize(job) or {}


def mark_job_running(job_id: str) -> None:
    now = utcnow()
    _collection().update_one(
        {"jobId": job_id},
        {
            "$set": {
                "status": "running",
                "progress": 10,
                "error": "",
                "startedAt": now,
                "updatedAt": now,
            },
            "$inc": {"attempts": 1},
        },
    )


def update_job_progress(job_id: str, progress: int) -> None:
    _collection().update_one(
        {"jobId": job_id},
        {"$set": {"progress": max(0, min(100, progress)), "updatedAt": utcnow()}},
    )


def mark_job_succeeded(job_id: str, result: dict[str, Any] | None = None) -> None:
    now = utcnow()
    _collection().update_one(
        {"jobId": job_id},
        {
            "$set": {
                "status": "succeeded",
                "progress": 100,
                "result": result or {},
                "error": "",
                "finishedAt": now,
                "updatedAt": now,
            }
        },
    )


def mark_job_failed(job_id: str, error: str) -> None:
    now = utcnow()
    _collection().update_one(
        {"jobId": job_id},
        {
            "$set": {
                "status": "failed",
                "error": error[:4000],
                "finishedAt": now,
                "updatedAt": now,
            }
        },
    )


def get_job(job_id: str) -> dict[str, Any] | None:
    return _serialize(_collection().find_one({"jobId": job_id}))
