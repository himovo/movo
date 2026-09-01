from __future__ import annotations

import socket
import urllib.parse
import urllib.request

from fastapi import APIRouter, Response, status

from app.core.config import settings
from app.core.db import get_db
from app.services.docling_runtime import docling_runtime_status
from app.workers.celery_app import celery_app

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "movo-document-processing-service"}


@router.get("/ready")
def ready(response: Response) -> dict:
    checks: dict[str, bool] = {}
    try:
        get_db().command("ping")
        checks["mongo"] = True
    except Exception:
        checks["mongo"] = False

    parsed = urllib.parse.urlparse(settings.redis_url)
    try:
        with socket.create_connection((parsed.hostname or "127.0.0.1", parsed.port or 6379), timeout=2):
            checks["redis"] = True
    except Exception:
        checks["redis"] = False

    try:
        with urllib.request.urlopen(f"{settings.weaviate_endpoint.rstrip('/')}/v1/.well-known/ready", timeout=2):
            checks["weaviate"] = True
    except Exception:
        checks["weaviate"] = False

    try:
        checks["worker"] = bool(celery_app.control.inspect(timeout=1).ping())
    except Exception:
        checks["worker"] = False

    checks["docling"], _ = docling_runtime_status()

    is_ready = all(checks.values())
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if is_ready else "degraded", "service": "movo-document-processing-service", "checks": checks}
