from __future__ import annotations

from typing import Any, Dict, List, Set
from urllib.parse import urlparse

from app.enterprise_capabilities.browser.engine.business_site_scope import url_mentions


_URL_TRAILING_STRIP = ".,;:!?)]}>\"'`、，。；：！？）】」』"


def extract_candidate_entries(
    original_user_request: str,
    visible_sites: List[Dict[str, Any]],
    *,
    expected_site: str = "",
) -> List[Dict[str, str]]:
    """Resolve browser entry URLs without confusing upstream resources.

    When orchestration supplies a target site scope, only URLs on that site
    are eligible browser entries.  Image/document URLs on other hosts remain
    task inputs and can never trigger the browser's first-navigation shortcut.
    """
    text = str(original_user_request or "")
    if not text:
        return []
    user_urls: List[str] = []
    mentions = list(url_mentions(text))
    for raw_url, _start, _end in mentions:
        url = _clean_url(raw_url)
        if url and url not in user_urls:
            user_urls.append(url)
    expected_host = str(expected_site or "").strip().lower().removeprefix("www.")
    if expected_host and not expected_host.startswith("profile:"):
        user_urls = [url for url in user_urls if _url_matches_site(url, expected_host)]
        if not user_urls and "." in expected_host:
            user_urls.append(f"https://{expected_host}/")
    user_hosts: Set[str] = set()
    for url in user_urls:
        try:
            host = urlparse(url).hostname
        except Exception:
            host = None
        if host:
            user_hosts.add(host)
    candidates: List[Dict[str, str]] = []
    for url in user_urls:
        synthesized = bool(
            expected_host
            and url == f"https://{expected_host}/"
            and not any(
                _url_matches_site(raw_url, expected_host)
                for raw_url, _start, _end in mentions
            )
        )
        candidates.append({
            "url": url,
            "source": "site_scope" if synthesized else "user_request",
            "name": expected_host if synthesized else "",
        })
    for profile in visible_sites or []:
        if not isinstance(profile, dict):
            continue
        name = str(profile.get("name") or "").strip()
        if not name or name not in text:
            continue
        entry_url = (
            str(profile.get("entry_url") or "").strip()
            or str(profile.get("domain") or "").strip()
        )
        if not entry_url:
            continue
        if not entry_url.lower().startswith("http"):
            entry_url = "https://" + entry_url
        if expected_host and not expected_host.startswith("profile:") and not _url_matches_site(
            entry_url, expected_host,
        ):
            continue
        try:
            site_host = urlparse(entry_url).hostname or ""
        except Exception:
            site_host = ""
        if site_host and site_host in user_hosts:
            continue
        candidates.append({"url": entry_url, "source": "site_profile", "name": name})
    return candidates


def _clean_url(raw: str) -> str:
    url = str(raw or "").rstrip(_URL_TRAILING_STRIP)
    while url.endswith(")") and url.count("(") < url.count(")"):
        url = url[:-1]
    return url


def _url_matches_site(url: str, site: str) -> bool:
    try:
        host = str(urlparse(str(url or "")).hostname or "").lower().removeprefix("www.")
    except Exception:
        return False
    expected = str(site or "").lower().removeprefix("www.")
    return bool(host and expected and (host == expected or host.endswith(f".{expected}")))


__all__ = ["extract_candidate_entries"]
