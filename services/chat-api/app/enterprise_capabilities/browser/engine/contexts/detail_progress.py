"""State-based detail-page progress detection for search workflows."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Sequence
from urllib.parse import parse_qsl, urlparse

from app.enterprise_capabilities.browser.engine.effect_verification.decision_target import resolve_coordinate_target
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


_SPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class DetailPageBaseline:
    url: str
    title: str
    content_fingerprint: str


@dataclass(frozen=True)
class DetailTargetFingerprint:
    source_url: str
    target_url: str
    labels: tuple[str, ...]
    scope_id: str = ""
    content_context_id: str = ""


def capture_detail_baseline(observation: Observation) -> DetailPageBaseline:
    return DetailPageBaseline(
        url=_normalise_url(observation.url),
        title=_normalise_text(observation.title),
        content_fingerprint=_content_fingerprint(observation.page_text),
    )


def detail_page_observed(
    baseline: Optional[DetailPageBaseline],
    observation: Observation,
    *,
    target: Optional[DetailTargetFingerprint] = None,
    known_page_urls: Iterable[str] = (),
) -> bool:
    """Return true when fresh state carries the object selected from a list.

    URL change alone is deliberately insufficient: back navigation, login and
    filter pages also change URLs.  A semantic target captured before the click
    must match the destination URL or visible object text.  Same-URL overlays
    remain detectable from a title + content transition.
    """
    if baseline is None:
        return False
    current_url = _normalise_url(observation.url)
    if not current_url.startswith(("http://", "https://")):
        return False
    known = {_normalise_url(value) for value in known_page_urls if value}
    if baseline.url and current_url != baseline.url:
        if current_url in known:
            return False
        if target is None:
            return False
        if target.target_url and same_detail_resource(target.target_url, current_url):
            return True
        return _target_text_present(target, observation)

    current_title = _normalise_text(observation.title)
    current_fingerprint = _content_fingerprint(observation.page_text)
    structural_overlay = bool(
        baseline.title
        and current_title
        and current_title != baseline.title
        and baseline.content_fingerprint
        and current_fingerprint
        and current_fingerprint != baseline.content_fingerprint
    )
    if not structural_overlay:
        return False
    return target is not None and _target_text_present(target, observation)


def capture_detail_target(
    decision: Decision,
    observation: Observation,
) -> Optional[DetailTargetFingerprint]:
    """Capture the business object selected by a click before dispatch."""
    if decision.tool not in {"browser_click", "browser_click_at", "browser_navigate", "browser_tab_new"}:
        return None
    args = dict(decision.args or {})
    target_url = str(args.get("url") or "").strip()
    if decision.tool in {"browser_navigate", "browser_tab_new"}:
        # A URL-bearing action is only a detail selection when that resource is
        # present in the current DOM. Otherwise an entry/list navigation would
        # prove itself as a detail merely because the destination URL matches
        # the requested URL after navigation.
        target = _observed_resource_target(target_url, observation.elements)
        if target is None:
            return None
    else:
        target = _resolve_target(args, observation.elements)
    if target:
        if target.get("editable") or target.get("semanticPurpose") == "search" or target.get("searchContext"):
            return None
        target_url = str(target.get("href") or target_url).strip()
        if not target_url:
            target_url = _nearest_related_resource_url(
                target,
                observation.elements,
            )
    content_context_id = str((target or {}).get("contentContextId") or "").strip()
    scope_lockable = bool((target or {}).get("scopeLockable"))
    labels = _target_labels(target or {})
    # Plain toolbar/filter buttons are UI transitions, not list resources.
    # Label-only targets remain supported when they belong to a deliberately
    # narrow, lockable content scope (for example a same-URL detail overlay).
    if not target_url and not content_context_id and not scope_lockable:
        return None
    if not target_url and not content_context_id and not labels:
        return None
    return DetailTargetFingerprint(
        source_url=_normalise_url(observation.url),
        target_url=_normalise_url(target_url),
        labels=labels,
        scope_id=_target_scope_identity(target or {}),
        content_context_id=content_context_id,
    )


def _observed_resource_target(
    target_url: str,
    elements: Sequence[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """Resolve a direct navigation back to a resource observed on this page."""
    if not str(target_url or "").strip():
        return None
    return next(
        (
            item
            for item in elements
            if isinstance(item, dict)
            and str(item.get("href") or "").strip()
            and same_detail_resource(str(item.get("href") or ""), target_url)
        ),
        None,
    )


def _resolve_target(args: dict[str, Any], elements: Sequence[dict[str, Any]]) -> Optional[dict[str, Any]]:
    ref = str(args.get("ref") or "").strip()
    if ref:
        return next((item for item in elements if str(item.get("ref") or "") == ref), None)
    if "x" not in args or "y" not in args:
        return None
    try:
        x, y = float(args["x"]), float(args["y"])
    except (TypeError, ValueError):
        return None
    candidates = [item for item in elements if item.get("href") or _target_labels(item)]
    return resolve_coordinate_target(candidates, (x, y), tolerance=24.0)


def _target_labels(target: dict[str, Any]) -> tuple[str, ...]:
    values = []
    for key in ("name", "text", "scopeName", "scopeText"):
        value = _normalise_text(target.get(key))
        if len(value) < 2 or value.lower() in {"submit", "search", "more"}:
            continue
        value = value[:240]
        if value not in values:
            values.append(value)
    return tuple(values[:3])


def _target_scope_identity(target: dict[str, Any]) -> str:
    """Return the narrowest stable DOM identity available for a list action."""
    return str(
        target.get("scopeId")
        or target.get("scopeSelector")
        or target.get("componentOwnerSelector")
        or target.get("selector")
        or ""
    ).strip()


def _nearest_related_resource_url(
    target: dict[str, Any],
    elements: Sequence[dict[str, Any]],
) -> str:
    """Bind a row action to the nearest resource link in the same DOM branch.

    Dynamic lists often render the business-object title as one link and an
    adjacent action (open, reply, edit) as a button without ``href``.  Refs and
    labels such as "open" are not object identities.  A uniquely nearest sibling
    resource link gives both controls the same durable target without relying on
    site names or action wording.
    """
    target_selector = str(target.get("selector") or "").strip()
    if not target_selector:
        return ""
    target_parts = _selector_parts(target_selector)
    if not target_parts:
        return ""

    ranked: list[tuple[int, str]] = []
    target_frame = int(target.get("frameDepth") or 0)
    for item in elements:
        if not isinstance(item, dict) or item is target:
            continue
        href = str(item.get("href") or "").strip()
        selector = str(item.get("selector") or "").strip()
        if (
            not href.startswith(("http://", "https://"))
            or not selector
            or int(item.get("frameDepth") or 0) != target_frame
        ):
            continue
        common_depth = _common_selector_depth(
            target_parts,
            _selector_parts(selector),
        )
        if common_depth:
            ranked.append((common_depth, href))

    if not ranked:
        return ""
    ranked.sort(key=lambda item: item[0], reverse=True)
    best_depth = ranked[0][0]
    best_urls = list(dict.fromkeys(
        href for depth, href in ranked if depth == best_depth
    ))
    second_depth = next(
        (depth for depth, _href in ranked if depth < best_depth),
        0,
    )
    specificity = best_depth / max(1, min(len(target_parts), max(
        len(_selector_parts(str(item.get("selector") or "")))
        for item in elements
        if isinstance(item, dict)
        and str(item.get("href") or "") in best_urls
    )))
    # A unique nearest branch must be materially more specific than the next
    # resource candidate. This avoids binding a page-level toolbar action to an
    # arbitrary navigation link.
    if (
        len(best_urls) != 1
        or best_depth < 2
        or specificity < 0.5
        or best_depth <= second_depth
    ):
        return ""
    return best_urls[0]


def _selector_parts(selector: str) -> tuple[str, ...]:
    return tuple(
        part.strip()
        for part in str(selector or "").split(">")
        if part.strip()
    )


def _common_selector_depth(
    left: Sequence[str],
    right: Sequence[str],
) -> int:
    depth = 0
    for left_part, right_part in zip(left, right):
        if left_part != right_part:
            break
        depth += 1
    return depth


def _target_text_present(target: DetailTargetFingerprint, observation: Observation) -> bool:
    corpus = _normalise_text(f"{observation.title}\n{observation.page_text}")
    if not corpus:
        return False
    return any(label in corpus for label in target.labels)


def same_detail_resource(left: str, right: str) -> bool:
    """Compare detail resources without substring collisions.

    Tracking/session parameters may legitimately change after navigation, but
    resource identifiers shared by both URLs must agree. This avoids treating
    ``/post/1`` as the same object as ``/post/10``.
    """
    try:
        left_url = urlparse(_normalise_url(left))
        right_url = urlparse(_normalise_url(right))
    except ValueError:
        return False
    if not left_url.hostname or not right_url.hostname:
        return False
    if left_url.hostname.casefold() != right_url.hostname.casefold():
        return False
    if left_url.port != right_url.port:
        return False
    left_path = left_url.path.rstrip("/") or "/"
    right_path = right_url.path.rstrip("/") or "/"
    if left_path != right_path:
        return False
    left_query = _resource_query(left_url.query)
    right_query = _resource_query(right_url.query)
    shared_keys = set(left_query).intersection(right_query)
    if left_query and right_query and not shared_keys:
        return False
    return all(left_query[key] == right_query[key] for key in shared_keys)


def _resource_query(value: str) -> dict[str, str]:
    ignored = {
        "token", "session", "sessionid", "sid", "source", "ref", "from",
        "timestamp", "ts", "track", "tracking", "spm",
    }
    return {
        key.casefold(): item
        for key, item in parse_qsl(value, keep_blank_values=False)
        if key and not key.casefold().startswith("utm_") and key.casefold() not in ignored
    }


def _normalise_url(value: str) -> str:
    return str(value or "").strip().rstrip("/")


def _normalise_text(value: str) -> str:
    return _SPACE.sub(" ", str(value or "")).strip()


def _content_fingerprint(value: str) -> str:
    text = _normalise_text(value)
    if not text:
        return ""
    return hashlib.sha256(text[:8000].encode("utf-8")).hexdigest()[:20]


__all__ = [
    "DetailPageBaseline",
    "DetailTargetFingerprint",
    "capture_detail_target",
    "capture_detail_baseline",
    "detail_page_observed",
    "same_detail_resource",
]
