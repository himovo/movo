"""Causal evidence for a search-result click that opens a detail page."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation

from .detail_progress import (
    DetailPageBaseline,
    DetailTargetFingerprint,
    capture_detail_baseline,
    capture_detail_target,
    detail_page_observed,
)
from .search_progress import (
    ObservedSearchResult,
    SearchBaseline,
    infer_search_result_from_observation,
    search_submission_confirmed,
)


@dataclass(frozen=True)
class SearchDetailCausalEvidence:
    search: ObservedSearchResult
    target: DetailTargetFingerprint
    baseline: DetailPageBaseline


def confirm_search_result_click(
    *,
    decision: Decision,
    before: Observation,
    after: Observation,
    search_baseline: Optional[SearchBaseline],
    expected_query: str,
    known_page_urls: Iterable[str] = (),
) -> Optional[SearchDetailCausalEvidence]:
    """Confirm both missed search progress and the resulting detail transition.

    This fallback is intentionally conjunctive: the pending search must expose
    a result surface relative to its pre-submit baseline, the action must target
    a concrete resource, and that resource must produce a matching detail page.
    """
    if decision.tool not in {"browser_click", "browser_click_at"}:
        return None
    query = str(expected_query or "").strip()
    observed_search = infer_search_result_from_observation(
        before,
        expected_query=query,
    )
    if (
        observed_search is None
        and search_baseline is not None
        and search_submission_confirmed(search_baseline, before, {})
    ):
        observed_search = ObservedSearchResult(
            query=query or search_baseline.query,
            url=str(before.url or ""),
        )
    if observed_search is None:
        return None

    target = capture_detail_target(decision, before)
    if target is None:
        return None
    baseline = capture_detail_baseline(before)
    if not detail_page_observed(
        baseline,
        after,
        target=target,
        known_page_urls=known_page_urls,
    ):
        return None
    return SearchDetailCausalEvidence(
        search=observed_search,
        target=target,
        baseline=baseline,
    )


__all__ = ["SearchDetailCausalEvidence", "confirm_search_result_click"]
