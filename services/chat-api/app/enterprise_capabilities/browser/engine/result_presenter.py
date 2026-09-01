"""Render browser action artifacts as a user-facing answer.

The browser planner returns two different channels on ``browser_done``:
``summary`` describes execution status, while ``data`` carries the observed
or confirmed result.  This module keeps that distinction explicit and turns
the structured result into deterministic Markdown without another LLM call.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List


_LABELS_ZH = {
    "result": "结果",
    "title": "标题",
    "page_title": "页面标题",
    "first_paragraph": "第一段正文",
    "final_url": "最终网址",
    "landed_ok": "页面已打开",
    "confirmation": "操作确认",
    "text": "页面提示",
    "record_id": "记录 ID",
    "redirect_url": "跳转网址",
    "changed_field": "修改字段",
    "new_value": "修改后内容",
    "removed_ref": "删除对象",
    "file": "文件",
    "direction": "传输方向",
    "path_or_url": "文件位置",
    "filename": "文件名",
    "size": "文件大小",
    "delivery": "发布结果",
    "channel": "发布渠道",
    "destination": "发布位置",
    "identifier": "发布标识",
}

_LABELS_EN = {
    "result": "Result",
    "title": "Title",
    "page_title": "Page title",
    "first_paragraph": "First paragraph",
    "final_url": "Final URL",
    "landed_ok": "Page opened",
    "confirmation": "Confirmation",
    "text": "Message",
    "record_id": "Record ID",
    "redirect_url": "Redirect URL",
    "changed_field": "Changed field",
    "new_value": "New value",
    "removed_ref": "Removed item",
    "file": "File",
    "direction": "Direction",
    "path_or_url": "File location",
    "filename": "Filename",
    "size": "File size",
    "delivery": "Delivery",
    "channel": "Channel",
    "destination": "Destination",
    "identifier": "Reference",
}

_INTERNAL_KEYS = {
    "browser_receipt",
    "screenshot",
    "screenshot_b64",
}
_MAX_VALUE_CHARS = 6000
_MAX_ANSWER_CHARS = 18000
_MAX_LIST_ITEMS = 50


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (dict, list, tuple)):
        return not value
    return False


def _visible_items(data: Dict[str, Any]) -> Iterable[tuple[str, Any]]:
    for raw_key, value in data.items():
        key = str(raw_key or "").strip()
        if not key or key.startswith("_") or key in _INTERNAL_KEYS or _is_empty(value):
            continue
        yield key, value


def _label(key: str, lang: str) -> str:
    labels = _LABELS_ZH if str(lang or "").startswith("zh") else _LABELS_EN
    return labels.get(key, key.replace("_", " ").strip().capitalize())


def _scalar(value: Any, lang: str) -> str:
    if isinstance(value, bool):
        if str(lang or "").startswith("zh"):
            return "是" if value else "否"
        return "Yes" if value else "No"
    text = str(value).strip()
    if len(text) > _MAX_VALUE_CHARS:
        suffix = "……（内容过长，已截断）" if str(lang or "").startswith("zh") else "... (truncated)"
        return text[:_MAX_VALUE_CHARS].rstrip() + suffix
    return text


def _render_mapping(data: Dict[str, Any], lang: str, *, depth: int = 0) -> List[str]:
    lines: List[str] = []
    for key, value in _visible_items(data):
        prefix = "  " * depth
        name = _label(key, lang)
        if isinstance(value, dict):
            nested = _render_mapping(value, lang, depth=depth + 1)
            if nested:
                lines.append(f"{prefix}- **{name}**")
                lines.extend(nested)
            continue
        if isinstance(value, (list, tuple)):
            nested = _render_list(list(value), lang, depth=depth + 1)
            if nested:
                lines.append(f"{prefix}- **{name}**")
                lines.extend(nested)
            continue
        lines.append(f"{prefix}- **{name}：**{_scalar(value, lang)}")
    return lines


def _render_list(values: List[Any], lang: str, *, depth: int = 0) -> List[str]:
    lines: List[str] = []
    prefix = "  " * depth
    for index, value in enumerate(values[:_MAX_LIST_ITEMS], 1):
        if _is_empty(value):
            continue
        if isinstance(value, dict):
            lines.append(f"{prefix}{index}.")
            lines.extend(_render_mapping(value, lang, depth=depth + 1))
        elif isinstance(value, (list, tuple)):
            lines.append(f"{prefix}{index}.")
            lines.extend(_render_list(list(value), lang, depth=depth + 1))
        else:
            lines.append(f"{prefix}{index}. {_scalar(value, lang)}")
    if len(values) > _MAX_LIST_ITEMS:
        omitted = len(values) - _MAX_LIST_ITEMS
        text = f"另有 {omitted} 项未展开" if str(lang or "").startswith("zh") else f"{omitted} more items omitted"
        lines.append(f"{prefix}- {text}")
    return lines


def render_browser_result(*, summary: str, data: Dict[str, Any], lang: str = "zh") -> str:
    """Combine status text and structured browser results for the end user."""
    clean_summary = str(summary or "").strip()
    visible_data = dict(_visible_items(data if isinstance(data, dict) else {}))
    if not visible_data:
        return clean_summary

    payload: Any = visible_data
    if set(visible_data) == {"result"}:
        payload = visible_data["result"]

    if isinstance(payload, dict):
        result_lines = _render_mapping(payload, lang)
    elif isinstance(payload, (list, tuple)):
        result_lines = _render_list(list(payload), lang)
    else:
        result_lines = [_scalar(payload, lang)]

    result_text = "\n".join(result_lines).strip()
    if not result_text:
        return clean_summary
    answer = f"{clean_summary}\n\n{result_text}" if clean_summary else result_text
    if len(answer) > _MAX_ANSWER_CHARS:
        suffix = "\n\n（结果过长，已截断）" if str(lang or "").startswith("zh") else "\n\n(Result truncated)"
        return answer[:_MAX_ANSWER_CHARS].rstrip() + suffix
    return answer
