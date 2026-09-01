from __future__ import annotations

from app.domain.jobs import IndexDocumentJobRequest
from app.repositories.job_repository import mark_job_failed, mark_job_running
from app.services.document_indexing_service import post_index_failure_callback, run_document_index
from app.workers.celery_app import celery_app


@celery_app.task(name="document.index", bind=True, max_retries=2)
def document_index_task(self, job_id: str, payload: dict) -> None:
    request = IndexDocumentJobRequest.model_validate(payload)
    try:
        mark_job_running(job_id)
        run_document_index(job_id, request)
    except Exception as exc:
        message = str(exc)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=15 * (self.request.retries + 1))
        mark_job_failed(job_id, message)
        post_index_failure_callback(job_id, request, message)
        raise
