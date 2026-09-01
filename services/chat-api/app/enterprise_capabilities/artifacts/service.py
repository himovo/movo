from __future__ import annotations

import os
from typing import Any

from app.enterprise_capabilities.spreadsheets import normalize_workbook_spec
from app.services.documents import document_service
from app.services.form_filling.docx_fill import fill_docx_form
from app.services.form_filling.xlsx_fill import fill_xlsx_form
from app.services.spreadsheets import spreadsheet_service
from app.services.translation.docx_inplace import translate_docx_inplace
from app.services.translation.xlsx_inplace import translate_xlsx_inplace
from app.enterprise_capabilities.runtime.contracts import CapabilityExecutionContext
from .references import require_owned_artifact
from .delivery_scope import apply_delivery_scope
from .storage import read_owned_artifact, upload_derived_artifact


def _source(arguments: dict[str, Any], context: CapabilityExecutionContext) -> tuple[dict[str, Any], bytes, str]:
    return read_owned_artifact(dict(arguments.get("artifact") or {}), context=context)


def _upload(content: bytes, *, context: CapabilityExecutionContext, filename: str, content_type: str) -> dict[str, Any]:
    return upload_derived_artifact(
        content,
        context=context,
        filename=filename,
        content_type=content_type,
    )


async def table_generate(arguments: dict[str, Any], context: CapabilityExecutionContext) -> dict[str, Any]:
    spec = normalize_workbook_spec(arguments.get("workbook"))
    result = await spreadsheet_service.render(spec, user_id=context.user_id, filename=str(arguments.get("filename") or "") or None)
    return {"success": True, "artifact": apply_delivery_scope(result, arguments.get("delivery_scope"))}


async def artifact_export(arguments: dict[str, Any], context: CapabilityExecutionContext) -> dict[str, Any]:
    output_format = str(arguments.get("format") or "").lower()
    if output_format == "xlsx":
        spec = normalize_workbook_spec(arguments.get("workbook"))
        result = await spreadsheet_service.render(
            spec, user_id=context.user_id, filename=str(arguments.get("filename") or "") or None,
        )
    elif output_format == "pptx":
        blueprint = str(require_owned_artifact(
            {"object_path": arguments.get("blueprint_object_path")}, user_id=context.user_id,
        ).get("object_path") or "").strip()
        if not blueprint:
            raise ValueError("blueprint_object_path is required for PPTX export")
        result = await document_service.render_presentation_pptx(
            user_id=context.user_id, blueprint_object_path=blueprint,
            filename=str(arguments.get("filename") or "") or None, title=str(arguments.get("title") or "") or None,
        )
        slide_count = int(result.get("slide_count") or 0)
        if slide_count <= 0:
            raise ValueError("PPTX export produced no slides")
        result = {
            **dict(result),
            "bundle": {
                "deck_ir_artifact": {"object_path": blueprint},
                "preview_metadata": {"blueprint_artifact_path": blueprint},
                "slide_count": slide_count,
            },
        }
    else:
        markdown = str(arguments.get("markdown") or "")
        if not markdown.strip():
            raise ValueError("markdown is required for document export")
        result = await document_service.render(
            markdown, user_id=context.user_id, format=output_format,
            filename=str(arguments.get("filename") or "") or None, title=str(arguments.get("title") or "") or None,
            skip_cover=bool(arguments.get("skip_cover")), skip_toc=bool(arguments.get("skip_toc")),
        )
    return {"success": True, "artifact": apply_delivery_scope(result, arguments.get("delivery_scope"))}


async def document_transform(arguments: dict[str, Any], context: CapabilityExecutionContext) -> dict[str, Any]:
    _artifact, source_bytes, source_name = _source(arguments, context)
    ext = os.path.splitext(source_name)[1].lower()
    kwargs = {
        "source_bytes": source_bytes, "source_language": str(arguments.get("source_language") or ""),
        "target_language": str(arguments.get("target_language") or ""),
    }
    if ext == ".docx":
        translated = await translate_docx_inplace(**kwargs)
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif ext in {".xlsx", ".xlsm"}:
        translated = await translate_xlsx_inplace(**kwargs)
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        raise ValueError("document_transform supports DOCX and XLSX artifacts")
    filename = str(arguments.get("filename") or f"translated_{source_name}")
    return {"success": True, "artifact": _upload(translated.file_bytes, context=context, filename=filename, content_type=content_type), "stats": translated.stats, "glossary": translated.glossary}


async def document_fill(arguments: dict[str, Any], context: CapabilityExecutionContext) -> dict[str, Any]:
    _artifact, source_bytes, source_name = _source(arguments, context)
    ext = os.path.splitext(source_name)[1].lower()
    from app.llm.factory import get_llm_client
    llm = get_llm_client(streaming=False, stage="compose")
    kwargs = {"source_bytes": source_bytes, "user_text": str(arguments.get("facts") or ""), "llm": llm, "overwrite": bool(arguments.get("overwrite"))}
    if ext == ".docx":
        filled = await fill_docx_form(**kwargs)
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif ext in {".xlsx", ".xlsm"}:
        filled = await fill_xlsx_form(**kwargs)
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        raise ValueError("table_fill supports DOCX and XLSX artifacts")
    filename = str(arguments.get("filename") or f"filled_{source_name}")
    return {"success": True, "artifact": _upload(filled.file_bytes, context=context, filename=filename, content_type=content_type), "stats": filled.stats, "warnings": filled.warnings}
