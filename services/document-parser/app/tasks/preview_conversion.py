from __future__ import annotations

from app.domain.jobs import PreviewConvertJobRequest
from app.repositories.job_repository import mark_job_failed, mark_job_running
from app.services.preview_conversion_service import post_preview_failure_callback, run_preview_conversion
from app.workers.celery_app import celery_app


@celery_app.task(name="document.preview_convert", bind=True, max_retries=2)
def preview_convert_task(self, job_id: str, payload: dict) -> None:
    request = PreviewConvertJobRequest.model_validate(payload)
    try:
        mark_job_running(job_id)
        run_preview_conversion(job_id, request)
    except Exception as exc:
        message = str(exc)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=10 * (self.request.retries + 1))
        mark_job_failed(job_id, message)
        post_preview_failure_callback(job_id, request, message)
        raise
