"""Causal boundary for delayed browser-effect verification."""
from __future__ import annotations

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision


_PASSIVE_TOOLS = {
    "browser_observe",
    "browser_read_text",
    "browser_screenshot",
    "browser_scroll",
    "browser_wait_for",
}


def breaks_pending_verification(decision: Decision) -> bool:
    """A new page interaction breaks attribution to an older pending action."""
    tool = str(decision.tool or "").strip()
    return bool(tool.startswith("browser_") and tool not in _PASSIVE_TOOLS and tool != "browser_done")


__all__ = ["breaks_pending_verification"]
