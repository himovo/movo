from __future__ import annotations

import json
import re
from typing import Any

from app.enterprise_capabilities.spreadsheets.models import SpreadsheetSpec


DEFAULT_SPREADSHEET_TITLES = {"", "spreadsheet", "excel", "xlsx", "excel表格", "工作簿", "表格"}


def is_default_spreadsheet_title(value: str) -> bool:
    return str(value or "").strip().lower() in DEFAULT_SPREADSHEET_TITLES


def safe_spreadsheet_filename(title: str) -> str:
    cleaned = str(title or "spreadsheet").strip()
    for token in ("\\", "/", ":", "*", "?", "\"", "<", ">", "|", "\n", "\r", "\t"):
        cleaned = cleaned.replace(token, "_")
    cleaned = "_".join(cleaned.split()) or "spreadsheet"
    if not cleaned.lower().endswith(".xlsx"):
        cleaned = f"{cleaned}.xlsx"
    return cleaned[:120]


def _compact_spec_context(spec: SpreadsheetSpec) -> dict[str, Any]:
    sheets = []
    for sheet in list(spec.sheets or [])[:5]:
        sheets.append(
            {
                "name": sheet.name,
                "columns": [col.title for col in list(sheet.columns or [])[:20]],
                "row_count": len(sheet.rows or []),
            }
        )
    return {
        "workbook_title": spec.workbook_title,
        "sheets": sheets,
    }


def _fallback_title_from_spec(spec: SpreadsheetSpec) -> str:
    sheet_names = [
        str(sheet.name or "").strip()
        for sheet in list(spec.sheets or [])[:2]
        if str(sheet.name or "").strip() and str(sheet.name or "").strip().lower() != "sheet1"
    ]
    if len(sheet_names) == 1:
        return sheet_names[0]
    if sheet_names:
        return "、".join(sheet_names) + "工作簿"
    first_sheet = (spec.sheets or [None])[0]
    if first_sheet:
        column_titles = [str(col.title or "").strip() for col in list(first_sheet.columns or [])[:3] if str(col.title or "").strip()]
        if column_titles:
            return "、".join(column_titles) + "表"
    return "spreadsheet"


async def _llm_title_from_spreadsheet_context(
    *,
    user_text: str,
    spec: SpreadsheetSpec,
    extra_context: str = "",
) -> str:
    payload = {
        "user_request": str(user_text or "").strip()[:2000],
        "spreadsheet_spec": _compact_spec_context(spec),
        "extra_context": str(extra_context or "").strip()[:3000],
    }
    text_for_language = json.dumps(payload, ensure_ascii=False)
    language = "zh" if re.search(r"[\u4e00-\u9fff]", text_for_language) else "en"
    if language == "zh":
        system = (
            "请为这个 Excel 工作簿生成一个简短、贴切的中文文件标题。"
            "如果用户请求里明确指定了文件名或标题，优先使用该名称；否则根据工作簿用途、sheet 名和列名命名。"
            "不要包含 .xlsx，不要加引号、书名号或解释，不要输出泛称如 spreadsheet、Excel表格、工作簿。"
            "标题不超过 18 个字，直接输出标题文字。"
        )
    else:
        system = (
            "Generate a short, descriptive Excel workbook title. "
            "If the user explicitly requested a filename or title, prefer that name; otherwise infer a title from the workbook purpose, sheet names, and columns. "
            "Do not include .xlsx, quotes, or explanations. Avoid generic titles like spreadsheet or workbook. "
            "Maximum 8 words. Return only the title."
        )
    try:
        from app.llm.factory import get_llm_client
        from app.llm.types import Message, Role

        llm = get_llm_client(streaming=False, stage="spreadsheet_title", intent="generation")
        resp = await llm.ainvoke(
            [
                Message(role=Role.SYSTEM, content=system),
                Message(role=Role.USER, content=json.dumps(payload, ensure_ascii=False)),
            ]
        )
        raw = getattr(resp, "content", resp)
        title = str(raw or "").strip().strip("\"'《》「」『』 \t\n")
        title = re.sub(r"^(?:标题|文件名|Title|Filename)\s*[:：]\s*", "", title, flags=re.IGNORECASE).strip()
        title = title.split("\n", 1)[0].strip()
        if title and not is_default_spreadsheet_title(title):
            return title[:120]
    except Exception:
        return ""
    return ""


async def resolve_spreadsheet_title(
    *,
    user_text: str,
    spec: SpreadsheetSpec,
    extra_context: str = "",
) -> str:
    current = str(spec.workbook_title or "").strip()
    if current and not is_default_spreadsheet_title(current):
        return current[:120]

    llm_title = await _llm_title_from_spreadsheet_context(
        user_text=user_text,
        spec=spec,
        extra_context=extra_context,
    )
    if llm_title:
        return llm_title

    return _fallback_title_from_spec(spec)[:120]
