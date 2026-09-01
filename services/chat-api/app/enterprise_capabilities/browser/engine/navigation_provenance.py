"""Ground model-issued browser navigation in URLs the runtime has seen.

The guard is deliberately narrow.  It prevents the common failure where the
planner invents a same-site route from a button label, while preserving the
legacy ability to bootstrap a task such as "open Baidu" when no URL source is
available at all.  Browser redirects and runtime-owned recovery navigation do
not pass through this policy.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable, Sequence
from urllib.parse import urljoin, urlsplit, urlunsplit


_ABSOLUTE_URL_RE = re.compile(r"https?://[^\s<>\[\]'\"`，。；？！：「」『』【】（）]+", re.I)
_TRAILING_PUNCTUATION = ".,;:!?)]}>\"'`、，。；：！？）】」』"
_UNRESERVED_ESCAPE_RE = re.compile(r"%([0-9a-fA-F]{2})")


@dataclass(frozen=True)
class NavigationProvenanceAssessment:
    allowed: bool
    reason: str
    source: str = ""
    audit_only: bool = False


def _normalize_percent_escapes(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        byte = int(match.group(1), 16)
        char = chr(byte)
        if (
            "a" <= char <= "z"
            or "A" <= char <= "Z"
            or "0" <= char <= "9"
            or char in "-._~"
        ):
            return char
        return f"%{match.group(1).upper()}"

    return _UNRESERVED_ESCAPE_RE.sub(replace, value)


def normalize_http_url(raw: Any, *, base_url: str = "") -> str:
    """Return a comparison-safe HTTP(S) URL, resolving relative hrefs."""
    text = str(raw or "").strip().rstrip(_TRAILING_PUNCTUATION)
    if not text:
        return ""
    try:
        absolute = urljoin(base_url, text) if base_url else text
        parsed = urlsplit(absolute)
    except Exception:
        return ""
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower().rstrip(".")
    if scheme not in {"http", "https"} or not host:
        return ""
    try:
        port = parsed.port
    except ValueError:
        return ""
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    rendered_host = f"[{host}]" if ":" in host else host
    netloc = rendered_host if port is None or default_port else f"{rendered_host}:{port}"
    path = _normalize_percent_escapes(parsed.path or "/")
    query = _normalize_percent_escapes(parsed.query)
    fragment = _normalize_percent_escapes(parsed.fragment)
    return urlunsplit((scheme, netloc, path, query, fragment))


def _origin(url: str) -> str:
    try:
        parsed = urlsplit(url)
    except Exception:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""


def _element_hrefs(observation: Any) -> Iterable[str]:
    for element in list(getattr(observation, "elements", None) or []):
        if not isinstance(element, dict):
            continue
        href = str(element.get("href") or "").strip()
        if href:
            yield href
        attributes = element.get("attributes")
        if isinstance(attributes, dict):
            nested = str(attributes.get("href") or "").strip()
            if nested:
                yield nested


def _observation_sources(observations: Iterable[Any]) -> dict[str, str]:
    sources: dict[str, str] = {}
    for observation in observations:
        if observation is None:
            continue
        base_url = normalize_http_url(getattr(observation, "url", ""))
        if base_url:
            sources.setdefault(base_url, "observed_location")
        for href in _element_hrefs(observation):
            normalized = normalize_http_url(href, base_url=base_url)
            if normalized:
                sources.setdefault(normalized, "observed_href")
        # Plain absolute URLs rendered as text are evidence too.  Relative
        # path-shaped prose is intentionally excluded because labels such as
        # "/statistics" are where route hallucinations become false evidence.
        page_text = str(getattr(observation, "page_text", "") or "")
        for match in _ABSOLUTE_URL_RE.findall(page_text):
            normalized = normalize_http_url(match)
            if normalized:
                sources.setdefault(normalized, "observed_text_url")
    return sources


def _explicit_sources(
    *,
    original_user_request: str,
    site_profiles: Sequence[dict[str, Any]],
    trusted_urls: Iterable[str],
) -> dict[str, str]:
    sources: dict[str, str] = {}
    request_text = str(original_user_request or "")
    for match in _ABSOLUTE_URL_RE.findall(request_text):
        normalized = normalize_http_url(match)
        if normalized:
            sources.setdefault(normalized, "user_request")
    for profile in site_profiles or ():
        if not isinstance(profile, dict):
            continue
        # The executor exposes every visible profile to the planner, but a
        # profile becomes authoritative for this task only when the user
        # actually named it. Otherwise an unrelated saved intranet profile
        # would make a name-only public-site task fail its first navigation.
        profile_name = str(profile.get("name") or "").strip()
        if not profile_name or profile_name not in request_text:
            continue
        for key in ("entry_url", "domain"):
            raw = str(profile.get(key) or "").strip()
            if raw and "://" not in raw:
                raw = "https://" + raw
            normalized = normalize_http_url(raw)
            if normalized:
                sources.setdefault(normalized, "site_profile")
    for raw in trusted_urls:
        normalized = normalize_http_url(raw)
        if normalized:
            sources.setdefault(normalized, "runtime_trusted")
    return sources


def assess_navigation_provenance(
    *,
    target_url: str,
    current_observation: Any,
    history_observations: Iterable[Any] = (),
    original_user_request: str = "",
    site_profiles: Sequence[dict[str, Any]] = (),
    trusted_urls: Iterable[str] = (),
    system_owned: bool = False,
) -> NavigationProvenanceAssessment:
    """Assess a planned navigation without treating redirects as decisions.

    Exact normalized matches are always accepted.  Ungrounded same-origin
    routes are blocked.  A first navigation that ignores an explicit user or
    site-profile entry is also blocked.  Cross-origin bootstrap navigation is
    audit-only for compatibility with name-only requests.
    """
    if system_owned:
        return NavigationProvenanceAssessment(True, "runtime-owned navigation", "runtime")

    current_url = normalize_http_url(getattr(current_observation, "url", ""))
    target = normalize_http_url(target_url, base_url=current_url)
    if not target:
        # Preserve existing handling for non-HTTP URLs; this guard is about
        # route provenance, not the browser tool's protocol validation.
        return NavigationProvenanceAssessment(True, "non-http navigation left to tool validation")

    explicit = _explicit_sources(
        original_user_request=original_user_request,
        site_profiles=site_profiles,
        trusted_urls=trusted_urls,
    )
    observed = _observation_sources((current_observation, *tuple(history_observations)))
    all_sources = {**observed, **explicit}
    if target in all_sources:
        return NavigationProvenanceAssessment(True, "target exactly matches a grounded URL", all_sources[target])

    target_origin = _origin(target)
    current_origin = _origin(current_url)
    explicit_origins = {_origin(url) for url in explicit}

    if explicit and not current_origin:
        return NavigationProvenanceAssessment(
            False,
            "initial navigation does not match any explicit user or site-profile URL",
        )
    if target_origin and (
        target_origin == current_origin
        or target_origin in explicit_origins
        or any(target_origin == _origin(url) for url in observed)
    ):
        return NavigationProvenanceAssessment(
            False,
            "same-site route was not present in any observed or explicit URL source",
        )
    if not all_sources:
        return NavigationProvenanceAssessment(
            True,
            "no URL source exists; preserving name-only bootstrap navigation",
            audit_only=True,
        )
    return NavigationProvenanceAssessment(
        True,
        "ungrounded cross-site navigation retained for compatibility",
        audit_only=True,
    )
