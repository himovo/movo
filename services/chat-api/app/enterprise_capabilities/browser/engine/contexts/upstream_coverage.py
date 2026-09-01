"""Resolve browser milestones already satisfied by upstream artifacts."""
from __future__ import annotations

import re
from typing import Set

from app.enterprise_capabilities.browser.engine.form_input.input_context import BrowserInputContext


_CLAUSE_BREAK = re.compile(r"[。；;，,\n]+")
_SEARCH_ACTION = re.compile(
    r"搜索|检索|查找|寻找|搜集|获取|下载|"
    r"\b(?:search|find|look\s+up|source|collect|download)\b",
    re.I,
)
_MEDIA_OBJECT = re.compile(
    r"配图|图片|图像|插图|素材|附件|文件|"
    r"\b(?:image|picture|photo|illustration|asset|attachment|file)s?\b",
    re.I,
)


def fulfilled_general_requirements(
    goal: str,
    input_context: BrowserInputContext,
) -> Set[str]:
    """Return browser outcomes already delivered by graph dependencies.

    A publishing node can inherit canonical media files while its natural
    language goal still says to find or download those files. The browser
    must upload them, but it should not wait for a redundant in-page search.
    """

    if not _has_upstream_files(input_context):
        return set()
    clauses = [
        clause.strip()
        for clause in _CLAUSE_BREAK.split(str(goal or ""))
        if clause.strip()
    ]
    if any(
        _SEARCH_ACTION.search(clause) and _MEDIA_OBJECT.search(clause)
        for clause in clauses
    ):
        return {"search"}
    return set()


def _has_upstream_files(input_context: BrowserInputContext) -> bool:
    return any(
        candidate.source_kind == "upstream"
        and candidate.value_kind == "file"
        and bool(list(candidate.value or []))
        for candidate in input_context.candidates
    )


__all__ = ["fulfilled_general_requirements"]
