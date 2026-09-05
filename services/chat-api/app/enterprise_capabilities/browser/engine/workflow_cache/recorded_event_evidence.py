from __future__ import annotations

from typing import Any, Mapping


def recorded_event_made_progress(event: Mapping[str, Any]) -> bool:
    """Return whether a recorded action crossed an observable page boundary."""
    before_tab = str(event.get("before_tab_id") or "")
    after_tab = str(event.get("after_tab_id") or "")
    if before_tab and after_tab and before_tab != after_tab:
        return True
    before_url = str(event.get("before_url") or event.get("url") or "")
    after_url = str(event.get("after_url") or event.get("url") or before_url)
    if before_url != after_url:
        return True
    before_fingerprint = str(event.get("before_fingerprint") or "")
    after_fingerprint = str(event.get("after_fingerprint") or "")
    return bool(
        before_fingerprint
        and after_fingerprint
        and before_fingerprint != after_fingerprint
    )


def unresolved_click_is_preparatory_fill(
    event: Mapping[str, Any],
    following: Mapping[str, Any] | None,
) -> bool:
    """Recognize an unlocatable presentation-layer click superseded by a fill.

    Rich editors commonly put a placeholder sibling over their actual editable
    node. Activating that sibling can change the DOM fingerprint, but replaying
    the following ``browser_fill`` already performs focus and input. URL, tab
    and authentication boundaries stay strict so an unknown navigation or
    login action is never silently discarded.
    """
    if str(event.get("type") or "").strip().casefold() != "unresolved_click":
        return False
    if not isinstance(following, Mapping):
        return False
    if str(following.get("type") or "").strip().casefold() != "fill":
        return False
    before_url = str(event.get("before_url") or event.get("url") or "")
    after_url = str(event.get("after_url") or event.get("url") or before_url)
    following_url = str(following.get("before_url") or following.get("url") or "")
    if not before_url or before_url != after_url or following_url != after_url:
        return False
    before_tab = str(event.get("before_tab_id") or "")
    after_tab = str(event.get("after_tab_id") or before_tab)
    following_tab = str(following.get("before_tab_id") or after_tab)
    if before_tab and after_tab and before_tab != after_tab:
        return False
    if after_tab and following_tab and after_tab != following_tab:
        return False
    before_auth = str(event.get("before_auth_state") or "unknown")
    after_auth = str(event.get("after_auth_state") or before_auth)
    if before_auth != after_auth:
        return False
    click_after = str(event.get("after_fingerprint") or "")
    fill_before = str(following.get("before_fingerprint") or "")
    return not click_after or not fill_before or click_after == fill_before


__all__ = ["recorded_event_made_progress", "unresolved_click_is_preparatory_fill"]
