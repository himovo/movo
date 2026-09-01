from __future__ import annotations

from typing import Any, Dict, Iterable

from .service import BrowserWorkflowCacheService


async def capture_manual_recording(
    *,
    cache: BrowserWorkflowCacheService,
    user_id: str,
    main_id: str,
    recording_id: str,
    operation: str,
    events: Iterable[Dict[str, Any]],
    variable_names: Dict[int, str] | None = None,
    display_name: str = "",
    capability_id: str = "",
) -> tuple[bool, str]:
    """Turn an explicitly confirmed human recording into the normal cache format."""
    # Local import avoids coupling the low-level candidate helpers to the
    # higher-level plan builder during module initialization.
    from .manual_plan import build_manual_recording_plan

    plan = build_manual_recording_plan(
        events=events,
        operation=operation,
        display_name=display_name,
        capability_id=capability_id,
        variable_names=variable_names,
    )
    if not plan.complete:
        return False, ",".join(plan.reasons[:5]) or "recording_incomplete"
    plan.node.node_id = f"manual-recording:{recording_id}"
    accepted = await cache.capture_success(
        user_id=user_id,
        main_id=main_id,
        node=plan.node,
        input_context=plan.context,
        history=plan.history,
        run_id=recording_id,
        replayed=False,
        trace_complete=True,
        display_name=plan.display_name,
    )
    return bool(accepted), ("accepted" if accepted else "coverage_incomplete")
__all__ = ["capture_manual_recording"]
