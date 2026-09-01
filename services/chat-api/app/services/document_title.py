from __future__ import annotations

import re
from typing import Any, Dict


_CJK_NUMERAL = "零〇一二三四五六七八九十百千万两"

_COMMON_SECTION_TITLES = {
    "摘要",
    "执行摘要",
    "结论摘要",
    "背景",
    "背景说明",
    "引言",
    "导语",
    "概述",
    "口径说明",
    "数据说明",
    "方法说明",
    "关键发现",
    "主要发现",
    "问题分析",
    "原因分析",
    "风险排序",
    "行动计划",
    "整改计划",
    "数据局限",
    "待确认事项",
    "结论",
    "总结",
    "附录",
    "executive summary",
    "summary",
    "abstract",
    "background",
    "introduction",
    "key findings",
    "findings",
    "methodology",
    "analysis",
    "recommendations",
    "action plan",
    "limitations",
    "conclusion",
    "appendix",
}


def is_source_document_heading(candidate: str) -> bool:
    text = str(candidate or "").strip().lower()
    return text.startswith(("spreadsheet:", "source spreadsheet:"))


def is_section_like_heading(candidate: str) -> bool:
    """Return True when a markdown H1 looks like a section heading, not a document title."""
    text = re.sub(r"\s+", " ", str(candidate or "").strip())
    if not text:
        return False
    normalized = text.strip("#：: 　").lower()
    if normalized in _COMMON_SECTION_TITLES:
        return True
    if re.match(rf"^[{_CJK_NUMERAL}]{{1,5}}[、.．]\s*\S+", normalized):
        return True
    if re.match(rf"^第[\d{_CJK_NUMERAL}]{{1,8}}[章节篇部分讲课]\b", normalized):
        return True
    if re.match(rf"^[（(][{_CJK_NUMERAL}\d]{{1,5}}[）)]\s*\S+", normalized):
        return True
    if re.match(r"^\d{1,2}(?:\.\d{1,2}){0,3}[、.．]\s*\S+", normalized):
        return True
    return False


def is_unreliable_markdown_title(candidate: str) -> bool:
    return is_source_document_heading(candidate) or is_section_like_heading(candidate)


def extract_reliable_markdown_h1(markdown: str) -> str:
    for line in str(markdown or "").splitlines():
        stripped = line.strip()
        if not stripped.startswith("# "):
            continue
        candidate = stripped[2:].strip()
        if candidate and not is_unreliable_markdown_title(candidate):
            return candidate[:120]
    return ""


def output_spec_title_hint(output_spec: Dict[str, Any]) -> str:
    spec = output_spec if isinstance(output_spec, dict) else {}
    preset = spec.get("profile_preset") if isinstance(spec.get("profile_preset"), dict) else {}
    metadata = preset.get("metadata") if isinstance(preset.get("metadata"), dict) else {}
    return str(metadata.get("title_hint") or "").strip()[:120]


def user_request_title_context(output_spec: Dict[str, Any]) -> str:
    spec = output_spec if isinstance(output_spec, dict) else {}
    values = [
        spec.get("inherited_user_request"),
        spec.get("user_request"),
        spec.get("user_question"),
        spec.get("original_user_request"),
    ]
    goal_contract = spec.get("goal_contract") if isinstance(spec.get("goal_contract"), dict) else {}
    values.extend([goal_contract.get("objective"), goal_contract.get("user_request")])
    for value in values:
        text = str(value or "").strip()
        if text:
            return text[:3000]
    return ""
