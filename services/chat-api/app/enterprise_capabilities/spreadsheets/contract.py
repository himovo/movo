from __future__ import annotations

import re
from typing import Any

from app.enterprise_capabilities.spreadsheets.models import SpreadsheetSpec


class WorkbookContractError(ValueError):
    """Raised when a model-provided workbook cannot produce a populated XLSX."""


_CELL_VALUE_SCHEMA = {
    "anyOf": [
        {"type": "string"},
        {"type": "number"},
        {"type": "integer"},
        {"type": "boolean"},
        {"type": "null"},
    ]
}


def workbook_input_schema() -> dict[str, Any]:
    """Return the canonical model-facing workbook schema.

    The runtime accepts a few common legacy/model aliases at its boundary, but
    only this canonical shape is advertised to DSH so the contract stays stable.
    """

    column = {
        "type": "object",
        "properties": {
            "key": {"type": "string", "minLength": 1, "maxLength": 80},
            "title": {"type": "string", "minLength": 1, "maxLength": 120},
            "type": {
                "type": "string",
                "enum": ["text", "number", "currency", "percent", "date", "boolean"],
            },
            "width": {"type": "integer", "minimum": 6, "maximum": 80},
            "number_format": {"type": "string", "minLength": 1, "maxLength": 80},
        },
        "additionalProperties": False,
        "required": ["key", "title"],
    }
    formatting = {
        "type": "object",
        "properties": {
            "freeze_header": {"type": "boolean"},
            "autofilter": {"type": "boolean"},
            "wrap_text": {"type": "boolean"},
            "auto_width": {"type": "boolean"},
        },
        "additionalProperties": False,
    }
    sheet = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "minLength": 1, "maxLength": 31},
            "columns": {"type": "array", "items": column, "minItems": 1},
            "rows": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": _CELL_VALUE_SCHEMA},
                "minItems": 1,
            },
            "formatting": formatting,
        },
        "additionalProperties": False,
        "required": ["name", "columns", "rows"],
    }
    return {
        "type": "object",
        "properties": {
            "workbook_title": {"type": "string", "minLength": 1, "maxLength": 120},
            "sheets": {"type": "array", "items": sheet, "minItems": 1},
        },
        "additionalProperties": False,
        "required": ["workbook_title", "sheets"],
    }


def _column_key(title: str, index: int, used: set[str]) -> str:
    base = re.sub(r"[^0-9A-Za-z_]+", "_", title).strip("_") or f"col_{index}"
    if base[0].isdigit():
        base = f"col_{base}"
    candidate = base[:80]
    suffix = 2
    while candidate in used:
        tail = f"_{suffix}"
        candidate = f"{base[:80 - len(tail)]}{tail}"
        suffix += 1
    used.add(candidate)
    return candidate


def _column_type(number_format: str) -> str:
    value = str(number_format or "").strip()
    if "%" in value:
        return "percent"
    if any(token in value for token in ("¥", "$", "€", "£")):
        return "currency"
    if value:
        return "number"
    return "text"


def _columns_from_table(table: dict[str, Any]) -> list[dict[str, Any]]:
    raw_columns = list(table.get("columns") or table.get("headers") or [])
    number_formats = dict((table.get("formats") or {}).get("number") or {})
    columns: list[dict[str, Any]] = []
    used: set[str] = set()
    for index, raw in enumerate(raw_columns, start=1):
        if isinstance(raw, dict):
            column = dict(raw)
            title = str(column.get("title") or column.get("header") or column.get("name") or f"列{index}")
            key = str(column.get("key") or column.get("field") or "").strip()
            if not key:
                key = _column_key(title, index, used)
            elif key in used:
                key = _column_key(key, index, used)
            else:
                used.add(key)
            column = {"key": key, "title": title, **{k: v for k, v in column.items() if k in {"type", "width", "number_format"}}}
        else:
            title = str(raw or f"列{index}").strip() or f"列{index}"
            column = {"key": _column_key(title, index, used), "title": title}
        number_format = str(number_formats.get(column["title"]) or number_formats.get(column["key"]) or "").strip()
        if number_format:
            column.setdefault("number_format", number_format)
            column.setdefault("type", _column_type(number_format))
        columns.append(column)
    return columns


def _table_to_sheet(table: dict[str, Any], *, sheet_name: str) -> dict[str, Any]:
    columns = _columns_from_table(table)
    formatting = dict(table.get("formatting") or {})
    freeze = str(table.get("freeze") or "").upper()
    if freeze:
        formatting["freeze_header"] = freeze == "A2"
    return {
        "name": sheet_name,
        "columns": columns,
        "rows": list(table.get("rows") or []),
        "formatting": formatting,
    }


def _normalize_aliases(raw: dict[str, Any]) -> dict[str, Any]:
    payload = dict(raw)
    normalized_sheets: list[dict[str, Any]] = []
    for sheet_index, raw_sheet in enumerate(list(payload.get("sheets") or []), start=1):
        if not isinstance(raw_sheet, dict):
            raise WorkbookContractError(f"workbook.sheets[{sheet_index - 1}] must be an object")
        sheet = dict(raw_sheet)
        tables = list(sheet.get("tables") or [])
        if not tables:
            normalized_sheets.append(sheet)
            continue
        if sheet.get("columns") or sheet.get("rows"):
            raise WorkbookContractError("a sheet cannot contain both columns/rows and tables")
        base_name = str(sheet.get("name") or f"Sheet{sheet_index}").strip() or f"Sheet{sheet_index}"
        for table_index, raw_table in enumerate(tables, start=1):
            if not isinstance(raw_table, dict):
                raise WorkbookContractError("workbook table must be an object")
            table_name = str(raw_table.get("name") or "").strip()
            target_name = base_name if len(tables) == 1 else (table_name or f"{base_name}_{table_index}")
            normalized_sheets.append(_table_to_sheet(dict(raw_table), sheet_name=target_name))
    payload["sheets"] = normalized_sheets
    return payload


def normalize_workbook_spec(raw: Any) -> SpreadsheetSpec:
    if not isinstance(raw, dict):
        raise WorkbookContractError("workbook must be an object")
    try:
        spec = SpreadsheetSpec.model_validate(_normalize_aliases(raw))
    except WorkbookContractError:
        raise
    except Exception as exc:
        raise WorkbookContractError(f"invalid workbook contract: {exc}") from exc

    if not spec.sheets:
        raise WorkbookContractError("workbook must contain at least one sheet")
    for sheet in spec.sheets:
        if not sheet.columns:
            raise WorkbookContractError(f"sheet '{sheet.name}' must contain at least one column")
        if not sheet.rows:
            raise WorkbookContractError(f"sheet '{sheet.name}' must contain at least one data row")
        keys = [column.key for column in sheet.columns]
        if len(keys) != len(set(keys)):
            raise WorkbookContractError(f"sheet '{sheet.name}' contains duplicate column keys")
    return spec
