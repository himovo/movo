"""Conservative local inference for repeated browser business operations."""
from __future__ import annotations

import re


_EXPLICIT_MULTIPLE = re.compile(
    r"多个|至少\s*[二两2]|依次|逐(?:个|条|篇)|每(?:个|条|篇|帖)|分别|批量|所有|"
    r"several|multiple|each|one\s+by\s+one|at\s+least\s+2",
    re.I,
)
_VAGUE_MULTIPLE = re.compile(r"一些|若干|几(?:个|条|篇|则|位)?|some\b|a\s+few\b", re.I)
_TARGET_SCOPE_PREFIX = re.compile(
    r"(?:进入(?:到)?|打开|选择|点击|对|给|在|处理|操作)\s*$|"
    r"(?:comment\s+on|reply\s+to|open|select)\s*$",
    re.I,
)
_BUSINESS_TARGET = re.compile(
    r"帖子|笔记|内容|结果|条目|问题|账号|用户|对象|商品|文章|评论区|"
    r"post|note|item|result|account|user|product|article",
    re.I,
)
_BUSINESS_OPERATION = re.compile(
    r"评论|回复|提交|发布|发表|发送|保存|创建|新增|修改|删除|点赞|收藏|"
    r"comment|reply|submit|publish|send|save|create|update|delete|like|favorite",
    re.I,
)
_SINGULAR_NARROWING = re.compile(
    r"(?:其中|任选|选择|挑选|只|仅).{0,12}(?:一|1)(?:个|条|篇|则|位)?|"
    r"(?:one|a\s+single)\s+(?:of|post|item|result)",
    re.I,
)


def minimum_business_effects(text: str, *, enabled: bool) -> int:
    """Return a safe minimum, not an unbounded execution count.

    Explicit repeat language keeps the established two-operation contract.
    Vague words such as ``一些`` count only when the nearby phrase also binds
    business objects to a mutation, and not when it narrows back to one item.
    """
    if not enabled:
        return 1
    source = " ".join(str(text or "").split())
    if _EXPLICIT_MULTIPLE.search(source):
        return 2
    for match in _VAGUE_MULTIPLE.finditer(source):
        prefix = source[max(0, match.start() - 20):match.start()]
        window = source[match.start():match.end() + 120]
        if (
            _TARGET_SCOPE_PREFIX.search(prefix)
            and _BUSINESS_TARGET.search(window)
            and _BUSINESS_OPERATION.search(window)
            and not _SINGULAR_NARROWING.search(window)
        ):
            return 2
    return 1


__all__ = ["minimum_business_effects"]
