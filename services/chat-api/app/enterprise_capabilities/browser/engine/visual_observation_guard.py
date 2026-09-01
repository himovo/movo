"""State-aware reuse guard for duplicate visual browser observations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import (
    Decision,
    Observation,
    StepRecord,
)


REDUNDANT_VISUAL_OBSERVATION = "redundant_visual_observation"


@dataclass(frozen=True)
class VisualObservationReuse:
    blocked: bool
    reason: str = ""


def _visual_scope(decision: Decision) -> tuple[str, bool, str, bool] | None:
    args = dict(decision.args or {})
    if decision.tool == "browser_observe":
        if not bool(args.get("with_screenshot")):
            return None
        return (
            "page",
            False,
            "",
            bool(args.get("with_hover_reveal")),
        )
    if decision.tool == "browser_screenshot":
        return (
            "page",
            bool(args.get("full_page")),
            str(args.get("ref") or ""),
            False,
        )
    return None


def redundant_visual_observation(
    decision: Decision,
    *,
    current: Observation,
    history: Iterable[StepRecord],
) -> VisualObservationReuse:
    """Block one immediate, identical screenshot request on unchanged state.

    The guard is deliberately narrow: it does not reuse screenshots after an
    action, wait, scroll, navigation, different capture scope, or failed
    visual observation. If the model repeats after receiving the explicit
    rejection once, execution is allowed to avoid turning a planner mistake
    into a hard loop.
    """
    requested_scope = _visual_scope(decision)
    if requested_scope is None or not current.screenshot:
        return VisualObservationReuse(blocked=False)

    records = list(history)
    if not records:
        return VisualObservationReuse(blocked=False)

    latest = records[-1]
    if (
        latest.error
        and str(latest.error).startswith(REDUNDANT_VISUAL_OBSERVATION)
    ):
        return VisualObservationReuse(blocked=False)
    if not latest.ok or _visual_scope(latest.decision) != requested_scope:
        return VisualObservationReuse(blocked=False)

    previous = latest.observation
    same_state = bool(
        current is previous
        or (
            current.state_fingerprint
            and previous.state_fingerprint
            and current.state_fingerprint == previous.state_fingerprint
            and current.url == previous.url
        )
    )
    if not same_state:
        return VisualObservationReuse(blocked=False)

    return VisualObservationReuse(
        blocked=True,
        reason=(
            f"{REDUNDANT_VISUAL_OBSERVATION}: the current page already has "
            "a screenshot from the immediately preceding observation and "
            "no page-changing action occurred; use that screenshot and "
            "choose the next task action"
        ),
    )


__all__ = [
    "REDUNDANT_VISUAL_OBSERVATION",
    "VisualObservationReuse",
    "redundant_visual_observation",
]
