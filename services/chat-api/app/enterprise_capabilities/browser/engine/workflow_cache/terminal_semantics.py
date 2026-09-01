from __future__ import annotations

from typing import Any, Mapping


TERMINAL_ACTION_TOKENS = (
    "save", "submit", "publish", "confirm", "delete", "complete",
    "send", "apply", "create", "update",
    "保存", "提交", "发布", "确认", "确定", "删除", "完成", "发送",
    "应用", "创建", "更新", "存草稿", "草稿",
)


def locator_has_terminal_intent(
    locator: Mapping[str, Any] | None,
    *,
    extra_text: str = "",
) -> bool:
    values = locator if isinstance(locator, Mapping) else {}
    text = " ".join(
        str(values.get(key) or "")
        for key in (
            "name", "text", "description", "semanticPurpose",
            "placeholder", "scopeName",
        )
    )
    corpus = f"{text} {extra_text}".casefold()
    return any(token in corpus for token in TERMINAL_ACTION_TOKENS)


__all__ = ["TERMINAL_ACTION_TOKENS", "locator_has_terminal_intent"]
