"""Choose whether a new browser run must honor its resolved entry URL."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


def initial_entry_url(
    *,
    step: int,
    candidates: List[Dict[str, Any]],
    current_url: str,
    resuming: bool,
) -> Optional[str]:
    """Return a grounded entry URL when the current tab is not valid for this run.

    A resumed human-assisted run keeps its current page. A new run with an
    explicit user URL must not inherit an unrelated page from the preceding
    browser task.
    """
    if step != 1 or len(candidates) != 1:
        return None
    candidate = candidates[0]
    target = str(candidate.get("url") or "").strip()
    if not target:
        return None
    current = str(current_url or "").strip()
    if current in {"", "about:blank"} or current.startswith("chrome-error://"):
        return target
    source = str(candidate.get("source") or "")
    if resuming or source not in {"target_url", "user_request", "site_scope"}:
        return None
    return None if _same_page(current, target) else target


def _same_page(left: str, right: str) -> bool:
    try:
        a, b = urlparse(left), urlparse(right)
    except Exception:
        return left == right
    host_a = str(a.hostname or "").lower().removeprefix("www.")
    host_b = str(b.hostname or "").lower().removeprefix("www.")
    path_a = (a.path or "/").rstrip("/") or "/"
    path_b = (b.path or "/").rstrip("/") or "/"
    return bool(host_a and host_a == host_b and path_a == path_b and a.query == b.query)


__all__ = ["initial_entry_url"]
