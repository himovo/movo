"""Lifecycle decisions for one selected business object.

This module extends the existing detail-target lock. It only interprets
navigation state; it does not classify websites, labels, or task types.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation

from .detail_progress import DetailTargetFingerprint, same_detail_resource


@dataclass(frozen=True)
class DetailCandidateOutcome:
    exclude: bool = False
    reason: str = ""


def classify_detail_candidate_return(
    *,
    target: DetailTargetFingerprint | None,
    detail_confirmed: bool,
    decision: Decision,
    before: Observation,
    after: Observation,
    requirements: Iterable[str],
    completed: Iterable[str],
) -> DetailCandidateOutcome:
    """Detect an unfinished candidate deliberately abandoned back to its source.

    A candidate is not rejected merely because its detail page lacks a known
    button. The planner must first leave the confirmed detail page and return to
    the source list while downstream requirements remain incomplete. This keeps
    the rule site-independent and avoids false negatives during normal editor
    discovery.
    """
    if target is None or not detail_confirmed:
        return DetailCandidateOutcome()
    if decision.tool not in {"browser_back", "browser_navigate"}:
        return DetailCandidateOutcome()
    if not before.fresh or not after.fresh:
        return DetailCandidateOutcome()
    if not target.source_url or not after.url:
        return DetailCandidateOutcome()
    if not same_detail_resource(target.source_url, after.url):
        return DetailCandidateOutcome()
    if same_detail_resource(target.source_url, before.url):
        return DetailCandidateOutcome()

    required = set(requirements)
    done = set(completed)
    pending_follow_up = [
        name for name in ("read", "commit")
        if name in required and name not in done
    ]
    if not pending_follow_up:
        return DetailCandidateOutcome()
    return DetailCandidateOutcome(
        exclude=True,
        reason=(
            "已进入该候选详情，但在完成"
            + "、".join(pending_follow_up)
            + "前返回了候选列表"
        ),
    )


__all__ = [
    "DetailCandidateOutcome",
    "classify_detail_candidate_return",
]
