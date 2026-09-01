"""Detect a possible form commit performed while the human owned the tab.

This is deliberately an *ask*, never an automatic success inference.  Its
purpose is to keep an untracked human-side submit from falling into the normal
effect-receipt loop, where no agent-prepared effect contract can ever exist.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlparse

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


_WRITE_CAPABILITIES = frozenset({
    "browser.publish",
    "browser.publish_or_submit",
    "browser.submit",
    "browser.modify",
})
_FORM_COMPONENT_KINDS = frozenset({"form_fill", "form_media", "form_commit"})
_STATUS_KEYS = frozenset({
    "published", "submitted", "saved", "success", "succeeded", "completed", "complete",
})
_POSITIVE_VALUES = frozenset({"1", "true", "yes", "ok", "success", "succeeded", "done", "completed"})
_SUCCESS_TEXT = (
    "发布成功", "提交成功", "保存成功", "已发布", "已提交", "已保存",
    "published successfully", "submitted successfully", "saved successfully",
)


@dataclass(frozen=True)
class HumanCommitReconciliation:
    should_ask: bool
    reason: str = ""
    evidence: tuple[str, ...] = ()


def assess_human_commit_reconciliation(
    *,
    capability_id: str,
    assistance_kind: str,
    human_outcome: str,
    before_url: str,
    after: Observation,
    form_state: Mapping[str, Any] | None,
    existing_receipts: list[Mapping[str, Any]] | None,
) -> HumanCommitReconciliation:
    """Return whether an untracked human commit needs explicit confirmation."""
    if (
        str(capability_id or "").strip().lower() not in _WRITE_CAPABILITIES
        or str(assistance_kind or "") not in _FORM_COMPONENT_KINDS
        or str(human_outcome or "").strip().lower() != "completed"
        or not after.fresh
        or existing_receipts
    ):
        return HumanCommitReconciliation(False)

    evidence: list[str] = []
    if _positive_status_in_url(after.url):
        evidence.append("post-human URL carries a positive commit status")
    corpus = " ".join((str(after.title or ""), str(after.page_text or ""))).casefold()
    if any(marker.casefold() in corpus for marker in _SUCCESS_TEXT):
        evidence.append("post-human page contains a commit-success signal")

    had_form_transaction = bool(list(dict(form_state or {}).get("fields") or []))
    editor_absent = not any(
        isinstance(item, dict)
        and bool(item.get("editable"))
        and item.get("visible") is not False
        for item in list(after.elements or [])
    )
    if had_form_transaction and editor_absent and _route_changed(before_url, after.url):
        evidence.append("the filled editor disappeared after a route transition")

    if not evidence:
        return HumanCommitReconciliation(False)
    return HumanCommitReconciliation(
        True,
        reason=(
            "人工接管期间页面出现了可能已保存或提交的变化，但该动作没有 Agent 回执"
        ),
        evidence=tuple(evidence),
    )


def _positive_status_in_url(url: str) -> bool:
    try:
        pairs = parse_qsl(urlparse(str(url or "")).query, keep_blank_values=True)
    except ValueError:
        return False
    return any(
        str(key or "").strip().casefold() in _STATUS_KEYS
        and str(value or "").strip().casefold() in _POSITIVE_VALUES
        for key, value in pairs
    )


def _route_changed(before_url: str, after_url: str) -> bool:
    before = urlparse(str(before_url or ""))
    after = urlparse(str(after_url or ""))
    return bool(
        before_url
        and after_url
        and (before.netloc, before.path, before.query) != (after.netloc, after.path, after.query)
    )


__all__ = ["HumanCommitReconciliation", "assess_human_commit_reconciliation"]
