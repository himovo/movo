from __future__ import annotations

import re
from typing import Any, Mapping

from app.enterprise_capabilities.browser.engine.form_input.input_context import InputCandidate


_ALIASES = {
    "title": ("title", "标题", "题目", "subject"),
    "subject": ("subject", "主题", "标题", "title"),
    "body": ("body", "正文", "内容", "content", "editor"),
    "content": ("content", "内容", "正文", "body", "editor"),
    "category": ("category", "分类", "栏目", "类别"),
    "media": ("media", "图片", "图像", "image", "上传", "upload"),
    "attachment": ("attachment", "附件", "file", "文件", "upload"),
    "recipient": ("recipient", "收件人", "接收人", "to"),
    "recipient_email": ("recipient", "email", "收件人", "邮箱"),
    "search_query": ("search", "query", "keyword", "搜索", "查询", "关键词"),
    "comment": ("comment", "reply", "feedback", "评论", "回复", "留言"),
    "name": ("name", "姓名", "名称"),
}
_LOCATOR_SEMANTIC_FIELDS = (
    "name", "text", "description", "placeholder", "semanticPurpose", "scopeName",
)


def locator_semantic_hint(locator: Mapping[str, Any]) -> str:
    return " ".join(
        str(locator.get(key) or "") for key in _LOCATOR_SEMANTIC_FIELDS
    ).strip()


def candidate_semantic_score(candidate: InputCandidate, hint: str) -> int:
    locator = str(hint or "").casefold()
    semantic = str(candidate.semantic_name or "").strip().casefold()
    tokens = _ALIASES.get(semantic, (semantic,))
    score = sum(20 for token in tokens if token and token.casefold() in locator)
    metadata = " ".join((
        str(candidate.semantic_name or ""),
        str(candidate.source_path or ""),
        str(candidate.candidate_id or ""),
    )).casefold()
    score += sum(
        4 for token in re.split(r"[^\w\u4e00-\u9fff]+", metadata)
        if token and token in locator
    )
    return score


__all__ = ["candidate_semantic_score", "locator_semantic_hint"]
