from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


CellValue = str | int | float | bool | None


class SpreadsheetColumnSpec(BaseModel):
    key: str = Field(..., min_length=1, max_length=80)
    title: str = Field(..., min_length=1, max_length=120)
    type: Literal["text", "number", "currency", "percent", "date", "boolean"] = "text"
    width: int | None = Field(default=None, ge=6, le=80)
    number_format: str | None = Field(default=None, min_length=1, max_length=80)


class SpreadsheetSheetSpec(BaseModel):
    name: str = Field(default="Sheet1", min_length=1, max_length=31)
    columns: List[SpreadsheetColumnSpec] = Field(default_factory=list)
    rows: List[Dict[str, CellValue]] = Field(default_factory=list)
    formatting: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_sheet_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        raw_columns = list(data.get("columns") or [])
        normalized_columns: List[Dict[str, Any]] = []
        aliases: List[tuple[str, str]] = []
        for index, item in enumerate(raw_columns, start=1):
            if isinstance(item, SpreadsheetColumnSpec):
                normalized_columns.append(item.model_dump())
                aliases.append((item.key, item.title))
                continue
            if not isinstance(item, dict):
                title = str(item or f"列{index}").strip() or f"列{index}"
                key = f"col_{index}"
                normalized_columns.append({"key": key, "title": title, "type": "text"})
                aliases.append((key, title))
                continue
            raw = dict(item)
            title = str(raw.get("title") or raw.get("header") or raw.get("name") or raw.get("label") or f"列{index}").strip()
            key = str(raw.get("key") or raw.get("field") or raw.get("id") or "").strip() or f"col_{index}"
            col_type = str(raw.get("type") or "text").strip().lower()
            if col_type in {"string", "str", "varchar"}:
                col_type = "text"
            elif col_type in {"integer", "int", "float", "decimal"}:
                col_type = "number"
            if col_type not in {"text", "number", "currency", "percent", "date", "boolean"}:
                col_type = "text"
            normalized = {
                "key": key,
                "title": title or key,
                "type": col_type,
            }
            if raw.get("width") is not None:
                normalized["width"] = raw.get("width")
            if raw.get("number_format") is not None:
                normalized["number_format"] = raw.get("number_format")
            normalized_columns.append(normalized)
            aliases.append((key, title or key))
        data["columns"] = normalized_columns

        raw_rows = list(data.get("rows") or [])
        normalized_rows: List[Dict[str, CellValue]] = []
        for row in raw_rows:
            if isinstance(row, dict):
                mapped: Dict[str, CellValue] = {}
                for key, title in aliases:
                    if key in row:
                        mapped[key] = row.get(key)
                    elif title in row:
                        mapped[key] = row.get(title)
                    else:
                        mapped[key] = None
                if mapped:
                    normalized_rows.append(mapped)
                else:
                    normalized_rows.append({str(k): v for k, v in row.items()})
                continue
            if isinstance(row, (list, tuple)):
                mapped = {}
                for index, cell in enumerate(row):
                    key = aliases[index][0] if index < len(aliases) else f"col_{index + 1}"
                    mapped[key] = cell
                normalized_rows.append(mapped)
        data["rows"] = normalized_rows
        if "formatting" not in data or not isinstance(data.get("formatting"), dict):
            data["formatting"] = {"freeze_header": True, "autofilter": True, "wrap_text": True, "auto_width": True}
        return data

    @field_validator("name")
    @classmethod
    def clean_sheet_name(cls, value: str) -> str:
        cleaned = str(value or "Sheet1").strip()
        for token in ("\\", "/", "?", "*", "[", "]", ":"):
            cleaned = cleaned.replace(token, "_")
        return (cleaned or "Sheet1")[:31]


class SpreadsheetSpec(BaseModel):
    workbook_title: str = Field(default="spreadsheet", max_length=120)
    sheets: List[SpreadsheetSheetSpec] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_workbook_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if not data.get("workbook_title"):
            data["workbook_title"] = (
                data.get("title")
                or data.get("workbook_name")
                or data.get("name")
                or data.get("filename")
                or "spreadsheet"
            )
        return data

    @field_validator("sheets")
    @classmethod
    def require_sheets(cls, value: List[SpreadsheetSheetSpec]) -> List[SpreadsheetSheetSpec]:
        return value or [SpreadsheetSheetSpec()]
