from __future__ import annotations

import re


_ROLE_ALIASES = {
    "title": {
        "title", "subject", "headline", "name",
        "标题", "主题", "文章标题", "邮件主题",
    },
    "body": {
        "body", "content", "message", "description", "article", "markdown", "report",
        "正文", "内容", "文章内容", "评论内容", "邮件正文", "描述", "备注",
    },
    "recipient": {
        "recipient", "receiver", "email", "email address",
        "收件人", "接收人", "邮箱", "邮件地址",
    },
    "attachment": {
        "attachment", "file", "image", "media",
        "附件", "文件", "图片", "配图", "媒体",
    },
}
_INPUT_PREFIX_RE = re.compile(
    r"^(?:请\s*)?(?:(?:在|于)(?:这里|此处|此)?\s*)?(?:输入|填写|键入|选择|上传)\s*|"
    r"^(?:(?:从|在)(?:这里|此处|此)?\s*)?开始\s*(?:输入|填写|写(?:入|作)?)\s*|"
    r"^(?:please\s+)?(?:enter|type|input|write|select|upload)\s+(?:a|an|the|your)?\s*|"
    r"^(?:start|begin)\s+(?:to\s+)?(?:enter|type|input|write|select|upload)(?:ing)?\s*",
    re.I,
)


def stable_placeholder_role(value: str) -> str:
    """Return a field role only for strict, generic placeholder labels.

    Rotating suggestions and sample values remain unclassified. The result is
    a semantic hint for binding; the placeholder is never used as field data.
    """

    normalized = _normalize(value)
    if not normalized:
        return ""
    stripped = _normalize(_INPUT_PREFIX_RE.sub("", normalized, count=1))
    for role, aliases in _ROLE_ALIASES.items():
        if stripped in aliases:
            return role
    return ""


def semantic_field_role(
    *,
    name: str = "",
    description: str = "",
    placeholder: str = "",
) -> str:
    """Classify an explicit field label without treating examples as identity."""

    for value in (name, description):
        normalized = _normalize(value)
        if not normalized:
            continue
        stripped = _normalize(_INPUT_PREFIX_RE.sub("", normalized, count=1))
        for role, aliases in _ROLE_ALIASES.items():
            if stripped in aliases:
                return role
    return stable_placeholder_role(placeholder)


def text_mentions_field_role(value: str, role: str) -> bool:
    """Return whether task text explicitly asks for a semantic field role."""

    normalized = _normalize(value)
    aliases = _ROLE_ALIASES.get(str(role or "").strip().lower(), set())
    for alias in aliases:
        token = _normalize(alias)
        if not token:
            continue
        if re.search(r"[\u4e00-\u9fff]", token):
            if token in normalized:
                return True
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", normalized):
            return True
    return False


def _normalize(value: str) -> str:
    token = re.sub(r"[\s:：*]+", " ", str(value or "")).strip().casefold()
    return token.rstrip("。.！!？?")


__all__ = [
    "semantic_field_role",
    "stable_placeholder_role",
    "text_mentions_field_role",
]
