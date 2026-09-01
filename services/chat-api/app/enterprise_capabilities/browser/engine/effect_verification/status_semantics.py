"""Shared semantic classification for concise browser status messages."""
from __future__ import annotations

import re
from typing import Literal


StatusPolarity = Literal["positive", "negative", "pending", "neutral"]

_STATUS_END = r"(?=$|[！!.。\s,，;；:：])"
_SUCCESS = re.compile(
    rf"(?:"
    rf"(?:操作|提交|发布|发送|保存|创建|新增|修改|更新|删除|评论|回复|"
    rf"上传|下载|审批|核销|处理)?(?:成功|已完成|操作完成){_STATUS_END}|"
    rf"(?<!未)(?<!尚未)已(?:成功)?(?:提交|发布|发送|保存|创建|新增|修改|更新|删除|"
    rf"评论|回复|上传|下载|审批|核销|处理){_STATUS_END}|"
    rf"\b(?:success(?:ful)?|completed|saved|submitted|published|sent|created|updated|deleted|uploaded)\b"
    rf")",
    re.I,
)
_UNAMBIGUOUS_OUTCOME = re.compile(
    r"成功|失败|已完成|未成功|操作完成|发生错误|被拒绝|"
    r"\b(?:success(?:ful)?|failed|failure|completed|error|rejected)\b",
    re.I,
)
_FAILURE = re.compile(
    rf"(?:"
    r"失败|未成功|发生错误|操作错误|被拒绝|"
    r"(?:请求|参数|系统|服务|网络|操作)?异常|"
    r"(?:请求|参数|操作|输入)?无效|"
    r"无法(?:完成|提交|发布|发送|保存|创建|新增|修改|更新|删除|处理|继续)|"
    r"不能(?:提交|发布|发送|保存|创建|新增|修改|更新|删除|处理|继续)|"
    r"不允许|不支持|已失效|已过期|"
    r"请(?:升级|刷新|稍后)?(?:客户端)?(?:后)?重试"
    rf"){_STATUS_END}|(?:"
    r"\b(?:failure|failed|error|exception|denied|rejected|invalid|"
    r"unsupported|expired|try again)\b|"
    r"\b(?:unable to|cannot|not allowed)\b"
    r")",
    re.I,
)
_PENDING = re.compile(
    r"^(?:正在|处理中|请稍候|排队中|sending|processing|pending|in progress)",
    re.I,
)
INLINE_STATUS = re.compile(
    r"(?:^|\s)(?:操作|提交|发布|发送|保存|创建|新增|修改|更新|删除|评论|回复|"
    r"上传|下载|审批|核销|处理)?(?:成功|失败|已完成|未成功|发生错误|被拒绝)"
    r"(?=\s|[！!.。,，；;]|$)|"
    r"(?<!未)(?<!尚未)已(?:成功)?(?:提交|发布|发送|保存|创建|新增|修改|更新|删除|"
    r"评论|回复|上传|下载|审批|核销|处理)(?=\s|[！!.。,，；;]|$)|"
    r"\b(?:success(?:ful)?|failed|failure|completed|submitted|published|sent|"
    r"saved|created|updated|deleted|rejected)\b",
    re.I,
)


def classify_status_text(value: str) -> StatusPolarity:
    """Classify a compact, newly observed status message.

    Callers are responsible for proving that the message is newly visible.
    Keeping temporal relevance outside this module avoids treating persistent
    page copy about errors or success as an operation result.
    """
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return "neutral"
    if _FAILURE.search(text):
        return "negative"
    if _SUCCESS.search(text):
        return "positive"
    if _PENDING.search(text):
        return "pending"
    return "neutral"


def is_unambiguous_outcome_text(value: str) -> bool:
    """Whether text alone is strong enough without a status-surface role."""

    return bool(_UNAMBIGUOUS_OUTCOME.search(" ".join(str(value or "").split())))


__all__ = [
    "INLINE_STATUS",
    "StatusPolarity",
    "classify_status_text",
    "is_unambiguous_outcome_text",
]
