from __future__ import annotations

from pathlib import Path
from typing import Any

from app.enterprise_capabilities.artifacts.delivery_scope import apply_delivery_scope
from app.enterprise_capabilities.artifacts.storage import read_owned_artifact, upload_derived_artifact
from app.enterprise_capabilities.runtime.contracts import CapabilityExecutionContext

from .page_retain import retain_pdf_pages


PDF_CONTENT_TYPE = "application/pdf"


def _output_filename(requested: Any, source_name: str) -> str:
    candidate = Path(str(requested or "").strip()).name
    if not candidate:
        source_stem = Path(source_name or "document.pdf").stem or "document"
        candidate = f"curated_{source_stem}.pdf"
    if not candidate.lower().endswith(".pdf"):
        candidate = f"{candidate}.pdf"
    return candidate


async def pdf_retain_pages(
    arguments: dict[str, Any],
    context: CapabilityExecutionContext,
) -> dict[str, Any]:
    _artifact, source_bytes, source_name = read_owned_artifact(
        dict(arguments.get("artifact") or {}),
        context=context,
    )
    if Path(source_name).suffix.lower() != ".pdf":
        raise ValueError("pdf_retain_pages supports PDF artifacts only")

    retained = retain_pdf_pages(source_bytes, list(arguments.get("keep_pages") or []))
    filename = _output_filename(arguments.get("filename"), source_name)
    artifact = upload_derived_artifact(
        retained.file_bytes,
        context=context,
        filename=filename,
        content_type=PDF_CONTENT_TYPE,
    )
    return {
        "success": True,
        "artifact": apply_delivery_scope(artifact, "final"),
        "selection": {
            "source_page_count": retained.source_page_count,
            "output_page_count": len(retained.kept_pages),
            "kept_pages": list(retained.kept_pages),
            "removed_pages": list(retained.removed_pages),
            "source_order_preserved": True,
            "source_unchanged": True,
            "warnings": list(retained.warnings),
        },
    }


__all__ = ["pdf_retain_pages"]
