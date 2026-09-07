"""Safe structured diagnostics for browser planner decisions."""
from __future__ import annotations

from typing import Any, Iterable


def summarize_actions(
    actions: Iterable[Any],
    elements: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Expose targets and search/navigation inputs without logging form data."""
    by_ref = {
        str(item.get("ref") or ""): item
        for item in elements
        if isinstance(item, dict) and item.get("ref")
    }
    summaries: list[dict[str, Any]] = []
    for action in actions:
        tool = str(getattr(action, "tool", "") or "")
        args = getattr(action, "args", {})
        args = args if isinstance(args, dict) else {}
        ref = str(args.get("ref") or "")
        target = by_ref.get(ref, {})
        summary: dict[str, Any] = {
            "tool": tool,
            "ref": ref,
            "role": str(target.get("role") or ""),
            "name": str(target.get("name") or "")[:160],
            "href": str(target.get("href") or "")[:500],
            "content_context_id": str(target.get("contentContextId") or "")[:240],
        }
        is_search_target = bool(
            target.get("searchContext") is True
            or str(target.get("role") or "").lower() == "searchbox"
            or str(target.get("semanticPurpose") or "") == "search"
        )
        if tool == "browser_fill" and is_search_target:
            summary["search_value"] = str(args.get("value") or "")[:240]
        elif tool in {"browser_navigate", "browser_tab_new"}:
            summary["url"] = str(args.get("url") or "")[:1000]
        elif tool == "browser_press":
            summary["key"] = str(args.get("key") or "")[:40]
        summaries.append(summary)
    return summaries


__all__ = ["summarize_actions"]
