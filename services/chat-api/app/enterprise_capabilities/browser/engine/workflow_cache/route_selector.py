from __future__ import annotations

from datetime import datetime
from typing import Iterable

from .contracts import CachedBrowserWorkflow


def select_replay_route(
    workflows: Iterable[CachedBrowserWorkflow],
) -> CachedBrowserWorkflow | None:
    """Choose the healthiest route after semantic intent matching.

    Semantic matching answers whether workflows perform the same business
    operation.  Route health is deterministic local state and must not be
    folded into an LLM confidence score.
    """

    candidates = list(workflows)
    if not candidates:
        return None
    return max(candidates, key=replay_route_rank)


def replay_route_rank(
    workflow: CachedBrowserWorkflow,
) -> tuple[int, int, int, datetime]:
    status_bonus = {
        "active": 5,
        "candidate": 0,
        "degraded": -20,
    }.get(workflow.status, -100)
    replay_successes = max(0, int(workflow.replay_success_count or 0))
    consecutive_failures = max(0, int(workflow.consecutive_failures or 0))
    score = (
        max(0, int(workflow.quality_score or 0))
        + status_bonus
        + min(replay_successes, 5) * 2
        - min(consecutive_failures, 3) * 10
    )
    return (
        score,
        replay_successes,
        max(0, int(workflow.success_count or 0)),
        workflow.updated_at,
    )


__all__ = ["replay_route_rank", "select_replay_route"]
