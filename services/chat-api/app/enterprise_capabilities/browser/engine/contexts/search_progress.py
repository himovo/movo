"""Evidence-based progress tracking for generic search interactions."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable
from urllib.parse import parse_qsl, unquote_plus, urlparse

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


@dataclass
class SearchBaseline:
    query: str
    url: str
    title: str
    link_targets: list[str] = field(default_factory=list)
    result_targets: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ObservedSearchResult:
    query: str
    url: str


def capture_search_baseline(query: str, observation: Observation) -> SearchBaseline:
    return SearchBaseline(
        query=str(query or "").strip(),
        url=str(observation.url or ""),
        title=str(observation.title or ""),
        link_targets=sorted(_link_targets(observation.elements)),
        result_targets=sorted(_result_targets(observation.elements)),
    )


def search_submission_confirmed(
    baseline: SearchBaseline | None,
    observation: Observation,
    _result: Any,
) -> bool:
    """Require observable result-page evidence, not merely an Enter/click."""
    if baseline is None or not baseline.query:
        return False
    if _looks_like_result_surface(observation.url, baseline.query, observation):
        return True

    baseline_results = set(baseline.result_targets) or {
        f"href:{target}" for target in baseline.link_targets
    }
    new_results = _result_targets(observation.elements) - baseline_results
    url_query = _query_from_url(observation.url)
    if (
        url_query
        and observation.url
        and observation.url != baseline.url
        and (
            _normalized_query(url_query) == _normalized_query(baseline.query)
            or _has_search_route(observation.url)
        )
    ):
        # This observation is causally tied to the just-submitted field. A
        # matching recognised query is enough even when a short result route
        # has no descriptive path and a compact accessibility snapshot omits
        # every result link. Explicit search routes retain the more tolerant
        # query handling needed by sites which normalise the submitted phrase.
        return True
    query_visible = _query_visible(baseline.query, observation)
    return query_visible and len(new_results) >= 1


def infer_observed_search_result(
    decision: Decision,
    observation: Observation,
) -> ObservedSearchResult | None:
    """Recognise a search result reached without a tracked field submit.

    Agents sometimes navigate to a site's result URL directly.  The progress
    ledger must still record that search, but only when the current URL carries
    a query and the live page exposes result-like links.  This deliberately
    relies on URL/DOM structure rather than site names.
    """
    return infer_search_result_from_observation(observation)


def infer_search_result_from_observation(
    observation: Observation,
    *,
    expected_query: str = "",
) -> ObservedSearchResult | None:
    """Infer a result surface from live page facts alone.

    Search engines and in-product search pages use many route shapes (short
    paths, hash routers, or no navigation at all).  A recognised query
    parameter is therefore stronger evidence than English words in the path.
    ``expected_query`` lets a context reconcile a fresh page after the action
    which produced it has fallen out of short planner history.
    """
    current_url = str(observation.url or "").strip()
    url_query = _query_from_url(current_url)
    expected = str(expected_query or "").strip()
    if (
        expected
        and url_query
        and _normalized_query(expected) != _normalized_query(url_query)
    ):
        return None
    query = expected or url_query or _query_from_search_field(observation)
    if not query or not _looks_like_result_surface(current_url, query, observation):
        return None
    return ObservedSearchResult(query=query, url=current_url)


def _link_targets(elements: Iterable[dict[str, Any]]) -> set[str]:
    return {
        str(item.get("href") or "").strip()
        for item in elements or []
        if isinstance(item, dict) and str(item.get("href") or "").strip()
    }


def _result_targets(elements: Iterable[dict[str, Any]]) -> set[str]:
    """Return stable result identities without requiring an href.

    Accessibility-tree observations can activate links by backend node id even
    when Chromium does not expose their URL. Search progress must use the same
    identity contract as the action layer instead of treating a missing href as
    proof that no result exists.
    """
    targets: set[str] = set()
    for item in elements or []:
        if not isinstance(item, dict) or str(item.get("role") or "").casefold() != "link":
            continue
        href = str(item.get("href") or "").strip()
        if href:
            targets.add(f"href:{href}")
            continue
        content_id = str(item.get("contentContextId") or "").strip()
        if content_id:
            targets.add(f"content:{content_id}")
            continue
        backend_id = str(item.get("backendNodeId") or "").strip()
        if backend_id:
            frame_depth = str(item.get("frameDepth") or 0)
            targets.add(f"ax:{frame_depth}:{backend_id}")
            continue
        label = " ".join(
            str(item.get(key) or "").strip()
            for key in ("name", "text")
            if str(item.get(key) or "").strip()
        )
        if label:
            targets.add(f"label:{label[:240].casefold()}")
    return targets


def _query_visible(query: str, observation: Observation) -> bool:
    corpus = " ".join(
        (str(observation.url or ""), str(observation.title or ""), str(observation.page_text or ""))
    )
    field_query = _query_from_search_field(observation)
    if field_query:
        corpus = f"{corpus} {field_query}"
    return _normalized_query(query) in _normalized_query(corpus)


def _query_from_url(url: str) -> str:
    try:
        parsed = urlparse(str(url or ""))
    except ValueError:
        return ""
    query_keys = {"q", "query", "keyword", "keywords", "search", "search_query", "wd", "text"}
    pairs = list(parse_qsl(parsed.query, keep_blank_values=False))
    # Hash-routed applications commonly place the query string after ``#``.
    fragment_query = parsed.fragment.partition("?")[2]
    if fragment_query:
        pairs.extend(parse_qsl(fragment_query, keep_blank_values=False))
    for key, value in pairs:
        if key.casefold() in query_keys and str(value).strip():
            return unquote_plus(str(value)).strip()[:240]
    return ""


def _query_from_search_field(observation: Observation) -> str:
    for item in observation.elements or []:
        if not isinstance(item, dict) or not item.get("editable"):
            continue
        purpose = str(item.get("semanticPurpose") or "").casefold()
        role = str(item.get("role") or "").casefold()
        if purpose != "search" and role != "searchbox":
            continue
        value = str(item.get("value") or "").strip()
        if value:
            return value[:240]
    return ""


def _looks_like_result_surface(
    url: str,
    query: str,
    observation: Observation,
) -> bool:
    results = _result_targets(observation.elements)
    if len(results) < 2:
        return False
    parsed_path = ""
    try:
        parsed_path = urlparse(url).path.casefold()
    except ValueError:
        pass
    query_visible = _query_visible(query, observation)
    search_surface = any(token in parsed_path for token in ("search", "query", "find", "result"))
    # A recognised URL query plus a populated link collection is itself a
    # generic result-surface contract. This covers short routes such as ``/s``
    # without naming or special-casing any search provider.
    url_query = _query_from_url(url)
    query_matches_url = bool(
        url_query
        and _normalized_query(url_query) == _normalized_query(query)
    )
    return query_visible and (query_matches_url or search_surface)


def _has_search_route(url: str) -> bool:
    try:
        path = urlparse(str(url or "")).path.casefold()
    except ValueError:
        return False
    return any(token in path for token in ("search", "query", "find", "result"))


def _normalized_query(value: str) -> str:
    return " ".join(str(value or "").casefold().split())


__all__ = [
    "ObservedSearchResult",
    "SearchBaseline",
    "capture_search_baseline",
    "infer_search_result_from_observation",
    "infer_observed_search_result",
    "search_submission_confirmed",
]
