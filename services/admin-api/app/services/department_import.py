from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any
from zipfile import ZipFile

from openpyxl import Workbook, load_workbook
from app.services.department_import_labels import EXAMPLES_BY_LANGUAGE, HEADERS_BY_LANGUAGE

HEADERS = ("department_name", "parent_path")
MAX_ROWS = 2000
MAX_BYTES = 2 * 1024 * 1024
MAX_DEPTH = 20


@dataclass(frozen=True)
class ImportRow:
    number: int
    name: str
    parent_path: str
    path: str


def template_bytes(root_name: str, language: str = "en") -> bytes:
    selected_language = "zh" if language.lower().startswith("zh") else "en"
    parent_name, child_name = EXAMPLES_BY_LANGUAGE[selected_language]
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Departments"
    sheet.append(HEADERS_BY_LANGUAGE[selected_language])
    sheet.append((parent_name, root_name))
    sheet.append((child_name, f"{root_name}/{parent_name}"))
    sheet.freeze_panes = "A2"
    sheet.column_dimensions["A"].width = 28
    sheet.column_dimensions["B"].width = 55
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def parse_workbook(content: bytes) -> list[ImportRow]:
    if len(content) > MAX_BYTES:
        raise ValueError("file_too_large")
    try:
        with ZipFile(BytesIO(content)) as archive:
            if sum(item.file_size for item in archive.infolist()) > 20 * 1024 * 1024:
                raise ValueError("file_too_large")
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
        sheet = workbook.active
        values = sheet.iter_rows(values_only=True)
        header = tuple(str(value or "").strip() for value in next(values, ()))
        if header[:2] not in (HEADERS, *HEADERS_BY_LANGUAGE.values()) or any(header[2:]):
            raise ValueError("invalid_headers")
        rows: list[ImportRow] = []
        for number, cells in enumerate(values, 2):
            if number > MAX_ROWS + 1:
                raise ValueError("too_many_rows")
            if not any(value is not None and str(value).strip() for value in cells):
                continue
            if len(cells) > 2 and any(value is not None and str(value).strip() for value in cells[2:]):
                raise ValueError("invalid_headers")
            name = str(cells[0] or "").strip()
            parent = str(cells[1] or "").strip() if len(cells) > 1 else ""
            rows.append(ImportRow(number, name, parent, f"{parent}/{name}" if parent else name))
        if not rows:
            raise ValueError("empty_workbook")
        workbook.close()
        return rows
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("invalid_workbook") from exc


def plan_import(rows: list[ImportRow], existing: list[dict[str, Any]], root_name: str) -> dict[str, Any]:
    known = {"/".join([*item.get("path_names", []), item.get("name", "")]): item for item in existing}
    candidates: dict[str, ImportRow] = {}
    errors: list[dict[str, Any]] = []
    for row in rows:
        error = ""
        if not row.name or len(row.name) > 64 or "/" in row.name or "\\" in row.name:
            error = "invalid_name"
        elif not row.parent_path or row.parent_path.startswith("/") or row.parent_path.endswith("/") or "//" in row.parent_path:
            error = "invalid_parent_path"
        elif not row.parent_path.startswith(root_name + "/") and row.parent_path != root_name:
            error = "invalid_root"
        elif len(row.path.split("/")) > MAX_DEPTH:
            error = "path_too_deep"
        elif row.path in candidates:
            error = "duplicate_row"
        if error:
            errors.append({"row": row.number, "path": row.path, "code": error})
        else:
            candidates[row.path] = row
    result: list[dict[str, Any]] = []
    for row in rows:
        if candidates.get(row.path) is not row:
            continue
        if row.path in known:
            result.append({"row": row.number, "path": row.path, "action": "skip"})
        elif row.parent_path not in known and row.parent_path not in candidates:
            errors.append({"row": row.number, "path": row.path, "code": "parent_not_found"})
        else:
            result.append({"row": row.number, "path": row.path, "action": "create"})
    result.sort(key=lambda item: (item["path"].count("/"), item["row"]))
    valid_paths = set(known)
    for item in result:
        if item["action"] == "skip":
            valid_paths.add(item["path"])
        elif item["path"].rsplit("/", 1)[0] in valid_paths:
            valid_paths.add(item["path"])
        else:
            errors.append({"row": item["row"], "path": item["path"], "code": "parent_not_found"})
    errors.sort(key=lambda item: item["row"])
    return {"items": result, "errors": errors, "createCount": sum(item["action"] == "create" for item in result), "skipCount": sum(item["action"] == "skip" for item in result)}
