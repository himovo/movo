from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "askai_document_processing",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.preview_conversion", "app.tasks.document_parsing", "app.tasks.document_indexing"],
)

celery_app.conf.update(
    task_default_queue=settings.celery_queue,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
)
