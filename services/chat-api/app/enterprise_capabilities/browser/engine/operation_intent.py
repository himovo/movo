from __future__ import annotations

import re
from typing import Any, Dict


_NEGATED_COMMIT = re.compile(
    r"(?:不要|禁止|不得|无需|不需要).{0,18}(?:最终|正式)?.{0,8}"
    r"(?:发布|提交|发送|保存|创建|确认)|"
    r"(?:do not|don't|must not|without).{0,20}"
    r"(?:finally\s+)?(?:publish|post|submit|send|save|create|confirm)",
    re.I,
)
_PREPARE_ONLY_CUE = re.compile(
    r"暂时|先|仅|只|停留|预览|草稿|待确认|不要点击|"
    r"for now|first|only|stop|stay|preview|draft|await(?:ing)? confirmation",
    re.I,
)
_FINAL_COMMIT_LABEL = re.compile(
    r"^(?:最终|正式|立即|确认)?\s*"
    r"(?:发布|提交|发送|保存|创建|确认发布|确认提交|确认发送)|"
    r"^(?:final(?:ly)?\s+|confirm\s+|send\s+now|publish\s+now)?"
    r"(?:publish|post|submit|send|save|create)$",
    re.I,
)


def stops_before_final_commit(text: str) -> bool:
    value = " ".join(str(text or "").split())
    return bool(
        value
        and _NEGATED_COMMIT.search(value)
        and _PREPARE_ONLY_CUE.search(value)
    )


def is_final_commit_control(target: Dict[str, Any]) -> bool:
    return any(
        bool(value and _FINAL_COMMIT_LABEL.fullmatch(value))
        for value in (
            " ".join(str(target.get(key) or "").split())
            for key in ("name", "text", "value", "aria_label")
        )
    )


__all__ = ["is_final_commit_control", "stops_before_final_commit"]
