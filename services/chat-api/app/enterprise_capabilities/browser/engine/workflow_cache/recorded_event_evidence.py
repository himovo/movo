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


__all__ = ["recorded_event_made_progress"]
