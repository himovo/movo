from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import settings
from app.core.security import verify_service_token
from app.domain.jobs import IndexDocumentJobRequest, IndexDocumentJobResponse
from app.repositories.job_repository import create_job, mark_job_failed
from app.tasks.document_indexing import document_index_task

router = APIRouter()


@router.post("/jobs/document-index", status_code=status.HTTP_202_ACCEPTED)
async def create_document_index_job(
    payload: IndexDocumentJobRequest,
    _: None = Depends(verify_service_token),
) -> IndexDocumentJobResponse:
    job_id = f"index_{uuid.uuid4().hex}"
    job_payload = payload.model_dump()
    create_job(job_id, "document_index", job_payload)
    try:
        document_index_task.apply_async(
            args=[job_id, job_payload],
            task_id=job_id,
            queue=settings.celery_queue,
        )
    except Exception as exc:
        mark_job_failed(job_id, str(exc))
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="任务队列不可用") from exc
    return IndexDocumentJobResponse(jobId=job_id, status="queued")
