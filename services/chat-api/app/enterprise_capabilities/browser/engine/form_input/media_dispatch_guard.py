from __future__ import annotations

from typing import Iterable

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation

from .input_context import BrowserInputContext
from .media_activation import (
    MediaActivationResolution,
    promote_media_control_decision,
)
from .media_delivery import prefers_media_paste
from .media_handoff import pending_media_candidates


def guard_media_dispatch(
    *,
    decision: Decision,
    observation: Observation,
    context: BrowserInputContext,
    completed_candidate_ids: Iterable[str],
) -> MediaActivationResolution:
    """Keep pending media actions on the upload path at final dispatch.

    This runs after executor-side wait/coordinate rewrites. A live media
    control is promoted to ``browser_upload_file``; a stale ref is refreshed
    instead of being sent as an ordinary click that could open a native file
    chooser.
    """

    paste_requested = prefers_media_paste(context.original_request)
    pending = pending_media_candidates(context, completed_candidate_ids)
    if paste_requested and pending and decision.tool == "browser_upload_file":
        return MediaActivationResolution(
            decision=Decision(
                tool="browser_observe",
                args={},
                rationale=(
                    "[form_media_dispatch] clipboard insertion was requested; "
                    "refresh the live rich editor and use browser_paste_image"
                ),
            ),
        )
    if decision.tool not in {"browser_click", "browser_click_at"}:
        return MediaActivationResolution()

    promoted = promote_media_control_decision(
        decision=decision,
        observation=observation,
        context=context,
        completed_candidate_ids=completed_candidate_ids,
    )
    if promoted.decision is not None:
        if paste_requested:
            return MediaActivationResolution(
                decision=Decision(
                    tool="browser_observe",
                    args={},
                    rationale=(
                        "[form_media_dispatch] the user requested clipboard "
                        "insertion; refresh the live editor and use "
                        "browser_paste_image instead of activating an upload control"
                    ),
                ),
            )
        return promoted

    if not pending or decision.tool != "browser_click":
        return MediaActivationResolution()

    ref = str((decision.args or {}).get("ref") or "").strip()
    if not ref or _has_live_ref(observation, ref):
        return MediaActivationResolution()

    return MediaActivationResolution(
        decision=Decision(
            tool="browser_observe",
            args={},
            rationale=(
                "[form_media_dispatch] pending media exists and the selected "
                "click ref is stale; refresh the editor before choosing an action"
            ),
        ),
    )


def _has_live_ref(observation: Observation, ref: str) -> bool:
    return any(
        isinstance(element, dict)
        and str(element.get("ref") or "").strip() == ref
        for element in list(observation.elements or [])
    )


__all__ = ["guard_media_dispatch"]
