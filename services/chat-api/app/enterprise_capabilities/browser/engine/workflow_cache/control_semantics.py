from __future__ import annotations

import re
from typing import Any, Mapping


_SELECTOR_TOKEN = re.compile(r"[a-z0-9\u4e00-\u9fff]+", re.I)
_SELECTOR_NOISE = {
    "body", "html", "main", "header", "footer", "section", "div", "span",
    "form", "input", "textarea", "button", "nth", "child", "of", "type",
}


def infer_control_semantic(
    target: Mapping[str, Any] | None,
    action: str = "",
    fallback_index: int = 0,
) -> str:
    """Infer a reusable input role from site-independent control signals."""
    values = target if isinstance(target, Mapping) else {}
    role = _normalized(values.get("role"))
    input_type = _normalized(values.get("type"))
    if role == "searchbox":
        return "search_query"
    if input_type == "file" or str(action or "").casefold() in {"upload", "paste_image"}:
        return "media"

    semantic_text = " ".join(
        str(values.get(key) or "")
        for key in (
            "name", "text", "description", "placeholder", "semanticPurpose",
            "scopeName", "aria_label", "ariaLabel", "autocomplete", "type",
        )
    ).casefold()
    selector_text = " ".join(
        token.casefold()
        for token in _SELECTOR_TOKEN.findall(str(values.get("selector") or ""))
        if token.casefold() not in _SELECTOR_NOISE and not token.isdigit()
    )
    corpus = f"{semantic_text} {selector_text}"
    groups = (
        ("search_query", ("search", "query", "keyword", "搜索", "查询", "关键词")),
        ("comment", ("comment", "reply", "feedback", "评论", "回复", "留言", "说点什么")),
        ("recipient_email", ("recipient", "email", "收件人", "邮箱")),
        ("title", ("title", "标题", "题目")),
        ("subject", ("subject", "主题")),
        ("media", ("upload", "image", "media", "attach", "file", "上传", "图片", "附件")),
        ("body", ("content", "editor", "正文", "内容", "编辑器")),
    )
    for semantic, tokens in groups:
        if any(_contains_token(corpus, token) for token in tokens):
            return semantic
    return f"field_{fallback_index + 1}"


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _contains_token(corpus: str, token: str) -> bool:
    if token.isascii():
        return bool(re.search(
            rf"(?<![a-z0-9]){re.escape(token.casefold())}(?![a-z0-9])",
            corpus,
        ))
    return token in corpus


__all__ = ["infer_control_semantic"]
