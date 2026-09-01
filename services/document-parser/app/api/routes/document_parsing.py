from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.security import verify_service_token
from app.domain.jobs import ParseDocumentJobRequest, ParseDocumentJobResponse, ParseMarkdownRequest, ParseMarkdownResponse
from app.repositories.job_repository import create_job, mark_job_failed
from app.services.markdown_parse_service import parse_markdown_sync
from app.tasks.document_parsing import document_parse_task

router = APIRouter()


@router.post("/jobs/document-parse", status_code=status.HTTP_202_ACCEPTED)
async def create_document_parse_job(
    payload: ParseDocumentJobRequest,
    _: None = Depends(verify_service_token),
) -> ParseDocumentJobResponse:
    job_id = f"parse_{uuid.uuid4().hex}"
    job_payload = payload.model_dump()
    create_job(job_id, "document_parse", job_payload)
    try:
        document_parse_task.apply_async(
            args=[job_id, job_payload],
            task_id=job_id,
            queue=settings.celery_queue,
        )
    except Exception as exc:
        mark_job_failed(job_id, str(exc))
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="任务队列不可用") from exc
    return ParseDocumentJobResponse(jobId=job_id, status="queued")


@router.post("/documents/parse-markdown", status_code=status.HTTP_200_OK)
async def parse_document_markdown(
    payload: ParseMarkdownRequest,
    _: None = Depends(verify_service_token),
) -> ParseMarkdownResponse:
    try:
        result = await run_in_threadpool(parse_markdown_sync, payload)
        return ParseMarkdownResponse.model_validate(result)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source document not found") from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
