from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple


EXTERNAL_WEB_RAW_TOOLS = {
    "progressive_research",
    "web_fetch",
    "firecrawl_collect_url",
}

_EXTERNAL_TEXT_MARKERS = (
    '"tool": "progressive_research"',
    '"tool":"progressive_research"',
    "'tool': 'progressive_research'",
    "### Deep Research Digest",
    "Sources Analyzed:",
)


def _normalize_tool_name(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def tool_name_from_record(record: Dict[str, Any]) -> str:
    candidates: List[Any] = [record.get("tool"), record.get("tool_name"), record.get("name")]
    nested = record.get("result") if isinstance(record.get("result"), dict) else {}
    candidates.extend([nested.get("tool"), nested.get("tool_name")])
    for item in candidates:
        token = _normalize_tool_name(item)
        if token:
            return token
    return ""


def is_external_web_raw_record(record: Any) -> bool:
    if not isinstance(record, dict):
        return False
    tool = tool_name_from_record(record)
    if tool in EXTERNAL_WEB_RAW_TOOLS:
        return True
    if "firecrawl" in tool or tool in {"web", "search", "web_search", "internet_search"}:
        return True
    return False


def _looks_like_external_web_raw_text(value: str) -> bool:
    text = str(value or "")
    if not text:
        return False
    if any(marker in text for marker in _EXTERNAL_TEXT_MARKERS):
        return True
    return bool(re.search(r'"(?:raw_tool_results|tool_results|decoded_payload)"\s*:', text) and "progressive_research" in text)


def _parse_jsonish(value: str) -> Any:
    text = str(value or "").strip()
    if not text or text[0] not in "[{":
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def _is_empty(value: Any) -> bool:
    return value in (None, "", [], {})


def strip_external_web_raw(value: Any, *, _depth: int = 0) -> Tuple[Any, int]:
    """Remove raw external-web search records while preserving KB/business data."""
    if _depth > 12:
        return value, 0

    if isinstance(value, dict):
        if is_external_web_raw_record(value):
            return None, 1
        cleaned: Dict[str, Any] = {}
        removed = 0
        for key, item in value.items():
            next_value, count = strip_external_web_raw(item, _depth=_depth + 1)
            removed += count
            if count and _is_empty(next_value):
                continue
            if not _is_empty(next_value):
                cleaned[str(key)] = next_value
        return cleaned, removed

    if isinstance(value, list):
        cleaned_items: List[Any] = []
        removed = 0
        for item in value:
            next_value, count = strip_external_web_raw(item, _depth=_depth + 1)
            removed += count
            if count and _is_empty(next_value):
                continue
            if not _is_empty(next_value):
                cleaned_items.append(next_value)
        return cleaned_items, removed

    if isinstance(value, str):
        parsed = _parse_jsonish(value)
        if parsed is not None:
            cleaned, removed = strip_external_web_raw(parsed, _depth=_depth + 1)
            if removed:
                return (json.dumps(cleaned, ensure_ascii=False) if not _is_empty(cleaned) else ""), removed
        if _looks_like_external_web_raw_text(value):
            return "", 1
        return value, 0

    return value, 0


_UPSTREAM_LINE_RE = re.compile(r"^(\s*-\s*[^:：]+[:：]\s*)([\[{].*)$")


def sanitize_external_web_raw_text(value: Any, *, item_limit: int = 1200) -> Tuple[str, int]:
    """Sanitize rendered upstream-artifact text that may contain JSON values."""
    text = str(value or "")
    if not text:
        return "", 0
    if "progressive_research" not in text and "Deep Research Digest" not in text:
        return text, 0

    removed_total = 0
    lines: List[str] = []
    raw_lines = text.splitlines()
    idx = 0
    while idx < len(raw_lines):
        raw_line = raw_lines[idx]
        if raw_line.startswith("# ") and idx + 1 < len(raw_lines) and raw_lines[idx + 1].lstrip().startswith(("{", "[")):
            block_lines: List[str] = []
            balance = 0
            cursor = idx + 1
            while cursor < len(raw_lines):
                block_line = raw_lines[cursor]
                block_lines.append(block_line)
                balance += block_line.count("{") + block_line.count("[")
                balance -= block_line.count("}") + block_line.count("]")
                cursor += 1
                if balance <= 0:
                    break
            parsed = _parse_jsonish("\n".join(block_lines))
            if parsed is not None:
                cleaned, removed = strip_external_web_raw(parsed)
                removed_total += removed
                if removed and _is_empty(cleaned):
                    idx = cursor
                    continue
                if removed:
                    rendered = json.dumps(cleaned, ensure_ascii=False, indent=2)
                    if len(rendered) > item_limit:
                        rendered = rendered[:item_limit] + "...<truncated>"
                    lines.extend([raw_line, rendered])
                    idx = cursor
                    continue

        line = raw_line
        match = _UPSTREAM_LINE_RE.match(raw_line)
        if match:
            parsed = _parse_jsonish(match.group(2).strip())
            if parsed is not None:
                cleaned, removed = strip_external_web_raw(parsed)
                removed_total += removed
                if removed and _is_empty(cleaned):
                    continue
                if removed:
                    rendered = json.dumps(cleaned, ensure_ascii=False)
                    if len(rendered) > item_limit:
                        rendered = rendered[:item_limit] + "...<truncated>"
                    line = match.group(1) + rendered
        elif _looks_like_external_web_raw_text(raw_line):
            removed_total += 1
            idx += 1
            continue
        lines.append(line)
        idx += 1

    return "\n".join(lines), removed_total
