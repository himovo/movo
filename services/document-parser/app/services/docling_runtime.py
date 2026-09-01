from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def artifacts_path() -> Path:
    return Path(os.environ.get("DOCLING_ARTIFACTS_PATH", "/opt/docling/models"))


def docling_runtime_status() -> tuple[bool, str]:
    try:
        from docling.document_converter import DocumentConverter  # noqa: F401
    except Exception as exc:
        return False, f"Docling import failed: {exc}"
    path = artifacts_path()
    if not path.is_dir() or not any(path.rglob("*")):
        return False, f"Docling model assets are missing: {path}"
    return True, str(path)


def pdf_pipeline_options() -> Any:
    from docling.datamodel.pipeline_options import PdfPipelineOptions

    return PdfPipelineOptions(artifacts_path=artifacts_path())
