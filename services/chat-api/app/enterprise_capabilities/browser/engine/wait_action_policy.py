from __future__ import annotations

from typing import Any, Mapping

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision


def should_resolve_wait_action(
    decision: Decision,
    *,
    ok: bool,
    result: Any,
) -> bool:
    """Only action-location waits may synthesize a follow-up click."""

    args = decision.args if isinstance(decision.args, Mapping) else {}
    return bool(
        decision.tool == "browser_wait_for"
        and ok
        and isinstance(result, Mapping)
        and not bool(args.get("probe_only"))
    )


__all__ = ["should_resolve_wait_action"]

