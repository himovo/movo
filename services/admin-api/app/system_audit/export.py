"""Bounded audit workbook export with literal text cells and tenant-scoped queries."""
from __future__ import annotations

import io
import re
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from app.api.audit_messages import localize_audit_page
from .export_messages import LABELS
from .query import SystemAuditQuery

MAX_EXPORT_ROWS = 10_000
MIME_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _text(value):
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]", "", str("" if value is None else value))
    return escape(text[:32767])


def workbook_bytes(items, language):
    headers = LABELS["en" if (language or "").lower().startswith("en") else "zh"]
    keys = ["occurredAt", "category", "module", "action", "actor", "target", "result"]
    rows = [headers] + [[item.get(key, "") for key in keys] for item in items]
    sheet_rows = []
    for number, values in enumerate(rows, 1):
        cells = ''.join(f'<c r="{chr(65 + col)}{number}" t="inlineStr"><is><t xml:space="preserve">{_text(value)}</t></is></c>' for col, value in enumerate(values))
        sheet_rows.append(f'<row r="{number}">{cells}</row>')
    sheet = f'<worksheet xmlns="{NS}"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" state="frozen"/></sheetView></sheetViews><cols><col min="1" max="7" width="24" customWidth="1"/></cols><sheetData>{"".join(sheet_rows)}</sheetData><autoFilter ref="A1:G{len(rows)}"/></worksheet>'
    output = io.BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        archive.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr('xl/workbook.xml', f'<workbook xmlns="{NS}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Audit" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        archive.writestr('xl/worksheets/sheet1.xml', sheet)
    return output.getvalue()


async def export_audit(*, main_id, category, keyword, result, module, language):
    page = await SystemAuditQuery().list_logs(main_id=main_id, category=category, page=1,
        page_size=MAX_EXPORT_ROWS + 1, keyword=keyword, result=result, module=module)
    if page["total"] > MAX_EXPORT_ROWS or len(page["items"]) > MAX_EXPORT_ROWS:
        raise HTTPException(status_code=413, detail="audit_export_limit_exceeded")
    return await run_in_threadpool(workbook_bytes, localize_audit_page(page, language)["items"], language)
