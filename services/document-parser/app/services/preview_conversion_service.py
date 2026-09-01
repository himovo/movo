from __future__ import annotations

import tempfile
from pathlib import Path

from app.domain.jobs import PreviewConvertJobRequest
from app.integrations.callbacks.admin_api_client import post_callback
from app.integrations.converters.libreoffice import convert_office_to_pdf
from app.integrations.storage import get_storage_adapter
from app.repositories.job_repository import mark_job_succeeded, update_job_progress


def run_preview_conversion(job_id: str, request: PreviewConvertJobRequest) -> None:
    source_storage = get_storage_adapter(request.source.storageType)
    target_storage = get_storage_adapter(request.target.storageType)
    with tempfile.TemporaryDirectory(prefix="askai-preview-") as temp_dir:
        temp_path = Path(temp_dir)
        suffix = Path(request.source.filename or request.source.storageKey).suffix or ".document"
        source_path = temp_path / f"source{suffix}"
        with source_storage.open_file(request.source.storageKey) as source, source_path.open("wb") as output:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
        update_job_progress(job_id, 35)

        pdf_path = convert_office_to_pdf(source_path, temp_path)
        update_job_progress(job_id, 75)
        with pdf_path.open("rb") as pdf_file:
            target_storage.put_file(pdf_file, request.target.storageKey)

    result = {
        "previewKey": request.target.storageKey,
        "previewMimeType": request.target.mimeType or "application/pdf",
    }
    update_job_progress(job_id, 90)
    post_callback(
        request.callback.url,
        request.callback.token,
        {
            "jobId": job_id,
            "status": "succeeded",
            "previewKey": result["previewKey"],
            "previewMimeType": result["previewMimeType"],
            "error": "",
        },
    )
    mark_job_succeeded(job_id, result)


def post_preview_failure_callback(job_id: str, request: PreviewConvertJobRequest, error: str) -> None:
    post_callback(
        request.callback.url,
        request.callback.token,
        {
            "jobId": job_id,
            "status": "failed",
            "previewKey": "",
            "previewMimeType": "",
            "error": error[:2000],
        },
    )
