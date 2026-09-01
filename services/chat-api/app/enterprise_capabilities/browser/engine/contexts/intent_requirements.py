"""Compile browser goals into evidence requirements without output/navigation ambiguity."""

from __future__ import annotations

import re
from typing import Set


_PATTERNS = {
    "navigate": re.compile(r"打开|访问|浏览|进入|open|visit|browse|navigate", re.I),
    "search": re.compile(r"搜索|检索|查找|search|look\s+up", re.I),
    "read": re.compile(r"读取|提取|获取|查看|总结|标题|正文|内容|read|extract|collect|summari[sz]e|title|content", re.I),
    # Chinese "返回结果/内容" means return data to the caller. Browser
    # history is required only with an explicit spatial target such as
    # "返回到搜索页", "回到列表" or "返回上一页".
    "return": re.compile(
        r"返回(?:到|至)(?=\s*(?:上一|原|搜索|列表|首页|前一|页面|页|https?://))|"
        r"返回(?:上一|原|首页|前一)(?:搜索|列表)?(?:结果)?页(?:面)?|"
        r"回到|回退|go\s+back|return\s+to",
        re.I,
    ),
    "commit": re.compile(
        r"评论|回复|提交|发布|发表|发送|保存|创建|新增|修改|删除|"
        r"\b(?:comment|reply|submit|publish|send|save|create|update|delete)\b|"
        r"\bpost\s+(?:a|the|this|your)\b",
        re.I,
    ),
}

_RESULT_SURFACE = re.compile(
    r"(?:打开|进入|访问|浏览|查看)[^，。；;\n]{0,32}"
    r"(?:搜索|检索)(?:的)?(?:结果)?(?:页面|页|列表)|"
    r"(?:open|visit|browse|view)[^,.;\n]{0,40}"
    r"(?:search|query)(?:\s+results?)?\s+(?:page|screen|list)",
    re.I,
)

_RESULT_SELECTION = re.compile(
    r"(?:打开|进入|选择|点击)"
    r"(?![^，。；;\n]{0,16}(?:按钮|搜索框|输入框))"
    r"[^，。；;\n]{0,24}(?:第[一二三四五六七八九十\d]+(?:条|个)?(?:搜索|检索)?结果|"
    r"结果中的?[^，。；;\n]{0,12}(?:条目|帖子|链接)|条目|详情|问题|帖子|链接)|"
    r"(?:open|select|click)"
    r"(?![^,.;\n]{0,24}(?:button|search\s+box|input))"
    r"[^,.;\n]{0,32}(?:first|second|third|\d+(?:st|nd|rd|th))?\s*"
    r"(?:search\s+result|result\s+item|item|detail|question|post|link)",
    re.I,
)

_NEGATED_RESULT_SELECTION = re.compile(
    r"(?:不要|请勿|禁止|不得|无需|无须|不必|避免|不可|不能)"
    r"[^，。；;\n]{0,32}(?:打开|进入|选择|点击|访问|浏览)"
    r"[^，。；;\n]{0,24}(?:结果|条目|详情|问题|帖子|笔记|链接)|"
    r"(?:do\s+not|don't|must\s+not|never|avoid)"
    r"[^,.;\n]{0,40}(?:open|enter|select|click|visit|browse)"
    r"[^,.;\n]{0,32}(?:result|item|detail|question|post|note|link)",
    re.I,
)

_LIST_ONLY = re.compile(
    r"(?:只|仅)(?:需|要)?(?:返回|读取|查看|浏览|提取)[^，。；;\n]{0,24}"
    r"(?:搜索|检索)?结果(?:页面|页|列表)?(?:信息|内容|数据)?|"
    r"(?:only|just)\s+(?:return|read|view|browse|extract)"
    r"[^,.;\n]{0,32}(?:search\s+)?results?(?:\s+(?:page|list|data|content))?",
    re.I,
)


def compile_general_requirements(goal: str) -> Set[str]:
    text = str(goal or "")
    found = {name for name, pattern in _PATTERNS.items() if pattern.search(text)}
    if _requires_result_selection(text):
        found.add("open_result")
    # Every browser task must at least establish a real page.
    found.add("navigate")
    return found


def _requires_result_selection(text: str) -> bool:
    """Distinguish opening a result item from opening the result surface.

    A search-results page is itself a navigation/read target.  Requiring a
    detail-page transition for phrases such as "open the search results page"
    makes a healthy list page impossible to complete and eventually triggers
    a false human handoff.
    """
    source = str(text or "")
    without_negated_selections = _NEGATED_RESULT_SELECTION.sub(" ", source)
    without_surfaces = _RESULT_SURFACE.sub(" ", without_negated_selections)
    if _LIST_ONLY.search(source) and not _RESULT_SELECTION.search(without_surfaces):
        return False
    return _RESULT_SELECTION.search(without_surfaces) is not None


__all__ = ["compile_general_requirements"]
