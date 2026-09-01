from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import settings
from app.core.security import verify_service_token
from app.domain.jobs import PreviewConvertJobRequest, PreviewConvertJobResponse
from app.repositories.job_repository import create_job, get_job, mark_job_failed
from app.tasks.preview_conversion import preview_convert_task

router = APIRouter()


@router.post("/jobs/preview-convert", status_code=status.HTTP_202_ACCEPTED)
async def create_preview_convert_job(
    payload: PreviewConvertJobRequest,
    _: None = Depends(verify_service_token),
) -> PreviewConvertJobResponse:
    job_id = f"preview_{uuid.uuid4().hex}"
    job_payload = payload.model_dump()
    create_job(job_id, "preview_convert", job_payload)
    try:
        preview_convert_task.apply_async(
            args=[job_id, job_payload],
            task_id=job_id,
            queue=settings.celery_queue,
        )
    except Exception as exc:
        mark_job_failed(job_id, str(exc))
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="任务队列不可用") from exc
    return PreviewConvertJobResponse(jobId=job_id, status="queued")


@router.get("/jobs/{job_id}")
async def get_processing_job(job_id: str, _: None = Depends(verify_service_token)) -> dict:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job
