from __future__ import annotations

from typing import Iterable

from app.enterprise_capabilities.research.progressive.json_utils import unique_strings
from app.enterprise_capabilities.research.progressive.models import ResearchTurnDecision


def is_semantically_empty_decision(decision: ResearchTurnDecision) -> bool:
    """Reject a decision that can neither produce evidence nor continue search.

    Rejections and rationale are diagnostic information, not an executable
    outcome. Even ``done=true`` cannot complete an evidence-backed task when
    the judge accepted no evidence.
    """

    return not decision.accepted_evidence and not decision.next_queries


def recovery_queries(
    *,
    research_goal: str,
    attempted_queries: Iterable[str],
    language: str,
    limit: int,
) -> list[str]:
    """Build a bounded second-round query when the judge returns no decision.

    This is a control-plane fallback, not evidence synthesis. It only broadens
    the original research goal and guarantees that an invalid judge response
    cannot silently terminate a progressive search after one round.
    """

    goal = " ".join(str(research_goal or "").split()).strip()
    attempted = [" ".join(str(item or "").split()).strip() for item in attempted_queries]
    attempted = [item for item in attempted if item]
    if str(language or "").startswith("zh"):
        suffixes = ("权威来源 实施案例 数据", "行业报告 实践路径 风险")
    else:
        suffixes = ("authoritative sources implementation case studies data", "industry report rollout risks")

    base = goal or (attempted[0] if attempted else "")
    candidates = [f"{base} {suffix}".strip() for suffix in suffixes]
    seen_attempted = {item.lower() for item in attempted}
    return [
        query
        for query in unique_strings(candidates, limit=max(1, limit))
        if query.lower() not in seen_attempted
    ]
