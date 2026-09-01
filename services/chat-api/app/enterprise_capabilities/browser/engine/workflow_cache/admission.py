from __future__ import annotations

from typing import Any, Iterable


_WRITE_CAPABILITIES = {
    "browser.submit", "browser.modify", "browser.delete",
    "browser.publish", "browser.publish_or_submit", "browser.file_transfer",
}


def terminal_effect_allows_cache(
    capability_id: str,
    receipts: Iterable[dict[str, Any]],
) -> bool:
    """Write workflows are admitted only by the final verified effect."""
    if str(capability_id or "").strip().lower() not in _WRITE_CAPABILITIES:
        return True
    items = [item for item in receipts if isinstance(item, dict)]
    return bool(items and str(items[-1].get("status") or "") == "confirmed_success")


__all__ = ["terminal_effect_allows_cache"]
