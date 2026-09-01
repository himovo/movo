from __future__ import annotations

import csv
import io
import json
import re
from typing import Any, Dict, List

from app.llm.types import Message, Role


def clean_user_fill_text(text: str) -> str:
    body = str(text or "").strip()
    for marker in ("[文档语义摘要]", "[文档Markdown]"):
        idx = body.find(marker)
        if idx > 0:
            body = body[:idx].strip()
    return body


def parse_user_data(text: str) -> Dict[str, Any]:
    body = clean_user_fill_text(text)
    key_values: Dict[str, str] = {}
    for line in body.splitlines():
        item = line.strip().strip("|")
        if not item:
            continue
        match = re.match(r"^([^:：=]{1,40})\s*[:：=]\s*(.+)$", item)
        if match:
            key = match.group(1).strip()
            value = match.group(2).strip()
            if key and value:
                key_values[key] = value

    records: List[Dict[str, str]] = []
    table_text = body
    if "\t" in table_text or "," in table_text:
        dialect = "excel-tab" if "\t" in table_text else "excel"
        try:
            rows = list(csv.reader(io.StringIO(table_text), dialect=dialect))
            rows = [[cell.strip() for cell in row] for row in rows if any(str(cell).strip() for cell in row)]
            if len(rows) >= 2 and len(rows[0]) >= 2:
                headers = rows[0]
                for row in rows[1:]:
                    records.append({headers[i]: row[i] for i in range(min(len(headers), len(row))) if headers[i]})
        except Exception:
            records = []

    return {"raw_text": body, "key_values": key_values, "records": records}


async def build_fill_plan(
    *,
    llm: Any,
    user_text: str,
    schema: Dict[str, Any],
    file_type: str,
    overwrite: bool = False,
) -> Dict[str, Any]:
    parsed = parse_user_data(user_text)
    fallback = deterministic_plan(parsed=parsed, schema=schema)
    system = (
        "You map user-provided data into an uploaded form/table schema.\n"
        "Return strict JSON only. Do not include markdown.\n"
        "Schema:\n"
        "{\n"
        "  \"fills\": [{\"target\":\"...\",\"value\":\"...\",\"label\":\"...\",\"confidence\":0.0}],\n"
        "  \"fill_rows\": [{\"target\":\"...\",\"rows\":[{\"Column\":\"Value\"}],\"confidence\":0.0}],\n"
        "  \"append_rows\": [{\"target\":\"...\",\"values\":{\"Column\":\"Value\"},\"confidence\":0.0}],\n"
        "  \"warnings\": [\"...\"]\n"
        "}\n"
        "Rules:\n"
        "- Use only targets present in the provided schema.\n"
        "- For xlsx fills, target must be a cell address target from fill_targets, e.g. Sheet1!B2.\n"
        "- For xlsx append_rows, target must be a table target from tables, e.g. Sheet1!table:3.\n"
        "- For docx fills, target must be a placeholder or cell target from fill_targets.\n"
        "- For docx row-style sections, prefer fill_rows using row_groups: split each logical record across its columns instead of putting the entire record into the first empty cell.\n"
        "- Prefer high-confidence exact label/header matches.\n"
        "- If the user asks to fill a resume/profile for a named public figure or organization, you may use generally known facts from your model knowledge; add a warning for uncertain or time-sensitive fields.\n"
        "- For sparse resume templates, populate section-title fields with concise section names and content fields with useful resume-ready text.\n"
        "- Do not overwrite existing non-empty values unless overwrite=true.\n"
        "- If unsure, omit the fill and add a warning.\n"
    )
    payload = {
        "file_type": file_type,
        "overwrite": overwrite,
        "user_data": parsed,
        "form_schema": schema,
    }
    try:
        resp = await llm.ainvoke(
            [
                Message(role=Role.SYSTEM, content=system),
                Message(role=Role.USER, content=json.dumps(payload, ensure_ascii=False)),
            ]
        )
        raw = str(getattr(resp, "content", "") or "").strip()
        data = json.loads(raw.replace("```json", "").replace("```", "").strip())
        if isinstance(data, dict):
            llm_has_output = bool(list(data.get("fills") or []) or list(data.get("append_rows") or []))
            fallback_has_output = bool(list(fallback.get("fills") or []) or list(fallback.get("append_rows") or []))
            if not llm_has_output and fallback_has_output:
                return fallback
            return data
    except Exception:
        pass
    return fallback


def deterministic_plan(*, parsed: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
    key_values = {str(k).strip().lower(): str(v).strip() for k, v in dict(parsed.get("key_values") or {}).items()}
    fills: List[Dict[str, Any]] = []
    used_labels: set[str] = set()
    for target in list(schema.get("fill_targets") or []):
        label = str(target.get("label") or target.get("name") or "").strip()
        label_key = label.lower()
        if label_key in used_labels:
            continue
        value = key_values.get(label.lower())
        if value:
            fills.append(
                {
                    "target": str(target.get("target") or "").strip(),
                    "label": label,
                    "value": value,
                    "confidence": 0.9,
                }
            )
            used_labels.add(label_key)
    append_rows: List[Dict[str, Any]] = []
    records = [r for r in list(parsed.get("records") or []) if isinstance(r, dict)]
    tables = [t for t in list(schema.get("tables") or []) if isinstance(t, dict)]
    if records and tables:
        table = tables[0]
        headers = {str(h).strip().lower(): str(h).strip() for h in list(table.get("headers") or [])}
        for record in records:
            values: Dict[str, str] = {}
            for key, value in record.items():
                canonical = headers.get(str(key).strip().lower())
                if canonical and str(value).strip():
                    values[canonical] = str(value).strip()
            if values:
                append_rows.append({"target": str(table.get("target") or ""), "values": values, "confidence": 0.85})
    return {"fills": fills, "append_rows": append_rows, "warnings": []}
