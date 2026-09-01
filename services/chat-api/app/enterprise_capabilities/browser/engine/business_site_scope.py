from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse


_HTTP_URL_RE = re.compile(
    r"https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+",
    re.IGNORECASE,
)
_BARE_DOMAIN_RE = re.compile(
    r"(?<![A-Za-z0-9@._-])(?:www\.)?(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,24}"
    r"(?:/[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]*)?",
    re.IGNORECASE,
)
_RESOURCE_SUFFIX_RE = re.compile(
    r"\.(?:png|jpe?g|gif|webp|svg|pdf|docx?|xlsx?|pptx?|zip|rar|7z|mp[34]|wav)(?:$|[?#])",
    re.IGNORECASE,
)
_OPERATION_CONTEXT_RE = re.compile(
    r"(?:浏览器(?:中)?打开|打开|访问|进入|登录|登陆|发布到|发表到|提交到|填写到|"
    r"navigate\s+to|open|visit|log\s*in(?:to)?|publish\s+to|submit\s+to)",
    re.IGNORECASE,
)
_RESOURCE_CONTEXT_RE = re.compile(
    r"(?:下载|图片|附件|文件|素材|资源|image|attachment|file|download)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class BusinessSiteScope:
    site_id: str = ""
    source: str = "unresolved"
    confidence: float = 0.0


def resolve_business_site_scope(
    node: Any,
    *,
    original_request: str = "",
    visible_sites: Sequence[Mapping[str, Any]] | None = None,
) -> BusinessSiteScope:
    """Resolve the destination system, not an upstream resource host.

    Explicit planner metadata always wins.  The fallback is deliberately
    conservative: it uses node-local URLs, named site profiles and contextual
    URL scoring, returning unresolved when two destinations remain ambiguous.
    """
    explicit = _explicit_scope(node)
    if explicit:
        return BusinessSiteScope(explicit, "planner", 1.0)

    node_goal = str(getattr(node, "goal", "") or "")
    profile = _profile_scope(original_request, visible_sites or ())
    candidates: dict[str, tuple[int, str]] = {}
    for text, source, base_score in (
        (node_goal, "node_goal", 150),
        (str(original_request or ""), "original_request", 0),
    ):
        for raw_url, start, end in url_mentions(text):
            site_id = canonical_site(raw_url)
            if not site_id:
                continue
            score = base_score + _context_score(text, raw_url, start, end)
            previous = candidates.get(site_id)
            if previous is None or score > previous[0]:
                candidates[site_id] = (score, source)
    if profile.site_id:
        candidates[profile.site_id] = max(
            candidates.get(profile.site_id, (-10_000, "")),
            (180, profile.source),
        )
    if not candidates:
        return BusinessSiteScope()
    ranked = sorted(
        ((score, site_id, source) for site_id, (score, source) in candidates.items()),
        reverse=True,
    )
    best_score, best_site, best_source = ranked[0]
    runner_up = ranked[1][0] if len(ranked) > 1 else -10_000
    if best_score < 40 or best_score - runner_up < 30:
        return BusinessSiteScope()
    confidence = 0.95 if best_score >= 140 else 0.8 if best_score >= 80 else 0.65
    return BusinessSiteScope(best_site, best_source, confidence)


def scope_node(
    node: Any,
    resolution: BusinessSiteScope,
) -> Any:
    """Return a TaskNode copy carrying the resolved scope when possible."""
    if not resolution.site_id or not hasattr(node, "model_copy"):
        return node
    meta = dict(getattr(node, "meta", None) or {})
    if str(meta.get("browser_site_scope") or "").strip():
        return node
    meta["browser_site_scope"] = resolution.site_id
    meta["browser_site_scope_source"] = resolution.source
    meta["browser_site_scope_confidence"] = resolution.confidence
    return node.model_copy(update={"meta": meta})


def resolve_site_from_history(history: Iterable[Any]) -> BusinessSiteScope:
    """Use the terminal successful browser state as cache-admission evidence."""
    hosts: list[str] = []
    for record in history:
        decision = getattr(record, "decision", None)
        tool = str(getattr(decision, "tool", "") or "")
        if tool in {"browser_done", "browser_fail", "browser_wait_for"}:
            continue
        for observation in (
            getattr(record, "resulting_observation", None),
            getattr(record, "observation", None),
        ):
            site = canonical_site(str(getattr(observation, "url", "") or ""))
            if site:
                hosts.append(site)
    if not hosts:
        return BusinessSiteScope()
    # Later business mutations are stronger evidence than an early resource
    # download or landing page. Repeated final hosts naturally win.
    final = hosts[-1]
    tail_support = sum(1 for host in hosts[-6:] if host == final)
    confidence = 0.95 if tail_support >= 2 else 0.8
    return BusinessSiteScope(final, "successful_trace", confidence)


def canonical_site(value: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    parsed = urlparse(text if "://" in text else f"//{text}")
    host = str(parsed.hostname or "").strip().lower().removeprefix("www.")
    return host or ""


def _explicit_scope(node: Any) -> str:
    direct = str(getattr(node, "browser_site_scope", "") or "").strip()
    meta = getattr(node, "meta", None)
    meta = meta if isinstance(meta, Mapping) else {}
    direct = direct or str(meta.get("browser_site_scope") or "").strip()
    if direct:
        return canonical_site(direct) or " ".join(direct.lower().split()).strip("/")
    site_context = meta.get("site_context") if isinstance(meta.get("site_context"), Mapping) else {}
    profile_id = str(site_context.get("site_profile_id") or site_context.get("id") or "").strip()
    if profile_id:
        return f"profile:{profile_id.lower()}"
    semantic = meta.get("semantic_config") if isinstance(meta.get("semantic_config"), Mapping) else {}
    workflow = meta.get("workflow_step") if isinstance(meta.get("workflow_step"), Mapping) else {}
    if not semantic and isinstance(workflow.get("semantic_config"), Mapping):
        semantic = workflow["semantic_config"]
    for value in (
        site_context.get("entry_url"),
        semantic.get("targetUrl"),
        semantic.get("target_url"),
    ):
        site = canonical_site(str(value or ""))
        if site:
            return site
    return ""


def _profile_scope(
    text: str,
    visible_sites: Sequence[Mapping[str, Any]],
) -> BusinessSiteScope:
    matches: list[str] = []
    for profile in visible_sites:
        name = str(profile.get("name") or "").strip()
        if not name or name not in str(text or ""):
            continue
        site = canonical_site(str(profile.get("entry_url") or profile.get("domain") or ""))
        if site and site not in matches:
            matches.append(site)
    if len(matches) == 1:
        return BusinessSiteScope(matches[0], "site_profile", 0.95)
    return BusinessSiteScope()


def url_mentions(text: str) -> Iterable[tuple[str, int, int]]:
    source = str(text or "")
    occupied: list[tuple[int, int]] = []
    for match in _HTTP_URL_RE.finditer(source):
        occupied.append((match.start(), match.end()))
        yield match.group(0).rstrip(".,;:!?)]}"), match.start(), match.end()
    for match in _BARE_DOMAIN_RE.finditer(source):
        if any(start <= match.start() < end for start, end in occupied):
            continue
        raw = match.group(0).rstrip(".,;:!?)]}")
        yield f"https://{raw}", match.start(), match.end()


def _context_score(text: str, url: str, start: int, end: int) -> int:
    before = text[max(0, start - 32):start]
    after = text[end:min(len(text), end + 32)]
    score = 0
    if _OPERATION_CONTEXT_RE.search(before[-24:]):
        score += 110
    if _RESOURCE_CONTEXT_RE.search(before[-16:] + after[:20]):
        score -= 70
    parsed = urlparse(url)
    if str(parsed.path or "") in {"", "/"}:
        score += 15
    if _RESOURCE_SUFFIX_RE.search(str(parsed.path or "")):
        score -= 90
    return score


__all__ = [
    "BusinessSiteScope",
    "canonical_site",
    "resolve_business_site_scope",
    "resolve_site_from_history",
    "scope_node",
    "url_mentions",
]
