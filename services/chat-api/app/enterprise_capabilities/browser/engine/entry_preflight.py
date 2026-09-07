"""Deterministic preflight for the first page of a browser mission."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


ENTRY_URL_REQUIRED = "entry_url_required"


@dataclass(frozen=True)
class EntryPreflight:
    ready: bool
    code: str = ""
    reason: str = ""


def assess_entry_preflight(
    *,
    current_url: str,
    candidates: Sequence[Mapping[str, Any]],
) -> EntryPreflight:
    """Reject only the state that cannot produce a grounded first action.

    A live page can be continued without an explicit URL.  A transient page
    can also proceed when at least one trusted entry candidate was resolved;
    the executor will navigate directly for a unique candidate or let the
    planner choose between multiple grounded candidates.  The only invalid
    state is a transient page with no grounded destination at all.
    """
    if not _is_transient_page(current_url):
        return EntryPreflight(ready=True)
    if any(str(item.get("url") or "").strip() for item in candidates):
        return EntryPreflight(ready=True)
    return EntryPreflight(
        ready=False,
        code=ENTRY_URL_REQUIRED,
        reason=(
            "The browser is on a transient blank/error page and the task has "
            "no grounded entry URL. Reissue browser_task with target_url, "
            "include an explicit URL in objective, or continue from a live page."
        ),
    )


def _is_transient_page(url: str) -> bool:
    value = str(url or "").strip().lower()
    return (
        not value
        or value == "about:blank"
        or value.startswith("chrome-error://")
        or value.startswith("data:text/html,chromewebdata")
    )


__all__ = ["ENTRY_URL_REQUIRED", "EntryPreflight", "assess_entry_preflight"]
