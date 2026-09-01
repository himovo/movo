"""Content-evidence rules shared by stateful browser contexts."""
from __future__ import annotations

from typing import Any, Optional, Set

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


def observed_content_text(
    decision: Decision,
    result: Any,
    observation: Observation,
    *,
    requirements: Set[str],
    completed: Set[str],
) -> Optional[str]:
    """Return text that proves the requested content was actually observed.

    ``browser_observe`` carries the same visible page text as ``read_text``.
    It is accepted only once the requested result/detail has been opened, so a
    search-results observation cannot accidentally satisfy a detail-read goal.
    """
    tool = str(decision.tool or "")
    if tool == "browser_read_text":
        text = str(result.get("text") or "") if isinstance(result, dict) else ""
        return text if text.strip() else None

    if tool not in {
        "browser_observe",
        "browser_click",
        "browser_click_at",
        "browser_navigate",
        "browser_tab_new",
    }:
        return None
    if "open_result" in requirements and "open_result" not in completed:
        return None
    text = str(observation.page_text or "")
    return text if text.strip() else None


__all__ = ["observed_content_text"]
