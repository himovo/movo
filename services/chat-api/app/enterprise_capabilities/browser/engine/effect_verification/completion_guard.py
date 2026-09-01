"""Completion policy for browser operations with external side effects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


_VERIFIED_WRITE_CAPABILITIES = frozenset({
    "browser.publish",
    "browser.publish_or_submit",
    "browser.submit",
    "browser.modify",
    "browser.delete",
})


@dataclass(frozen=True)
class EffectCompletionDecision:
    allowed: bool
    reason: str = ""


def assess_effect_completion(
    capability_id: str,
    receipts: Iterable[dict[str, Any]],
    *,
    lang: str,
) -> EffectCompletionDecision:
    capability = str(capability_id or "").strip().lower()
    if capability not in _VERIFIED_WRITE_CAPABILITIES:
        return EffectCompletionDecision(allowed=True)
    items = list(receipts)
    if any(str(item.get("status") or "") == "confirmed_success" for item in items):
        return EffectCompletionDecision(allowed=True)
    if any(str(item.get("status") or "") == "confirmed_failure" for item in items):
        reason = (
            "写入操作已被页面确认为失败，不能把任务报告为成功。请根据失败信息修正后重试。"
            if lang.startswith("zh") else
            "The page confirmed that the write failed. Do not report success; correct the failure before retrying."
        )
        return EffectCompletionDecision(allowed=False, reason=reason)
    reason = (
        "尚未取得发布/提交成功的业务回执。填写内容、投递点击或焦点变化都不等于发布成功；"
        "请使用可识别的提交控件执行操作，并观察成功提示、结果页或业务对象回查结果。"
        if lang.startswith("zh") else
        "No confirmed business receipt exists for this write. Filled text, a dispatched click, or focus change does not prove success; "
        "use an identifiable commit control and verify a success message, result page, or resulting object."
    )
    return EffectCompletionDecision(allowed=False, reason=reason)


__all__ = ["EffectCompletionDecision", "assess_effect_completion"]
