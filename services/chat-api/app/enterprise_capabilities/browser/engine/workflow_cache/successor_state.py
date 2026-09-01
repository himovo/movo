from __future__ import annotations

from enum import Enum
from typing import Callable

from app.enterprise_capabilities.browser.engine.action_target import locator_match_score
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation

from .contracts import CachedParameterBinding, CachedWorkflowStep
from .replay_evidence import cached_target_is_ready, resolved_wait_text
from .target_state import element_is_usable


class SuccessorState(str, Enum):
    ABSENT = "absent"
    PRESENT_NOT_READY = "present_not_ready"
    ACTIONABLE = "actionable"


def classify_successor(
    step: CachedWorkflowStep | None,
    observation: Observation,
    resolve: Callable[[CachedParameterBinding], object | None],
    *,
    before: Observation | None = None,
) -> SuccessorState:
    """Separate exact target presence from readiness to receive an action.

    A disclosed menu item can exist for a few animation frames before hit
    testing succeeds.  Presence is deliberately based on exact locator
    identity, never page/ancestor text containment.
    """

    if step is None:
        return SuccessorState.ABSENT
    if cached_target_is_ready(step, observation, resolve, before=before):
        return SuccessorState.ACTIONABLE
    if step.tool == "browser_wait_for":
        text = resolved_wait_text(step, resolve)
        if text and any(
            element_is_usable(element, require_hit_target=False)
            and _exact_label(element, text)
            for element in observation.elements
        ):
            return SuccessorState.PRESENT_NOT_READY
        return SuccessorState.ABSENT
    locator = _resolved_locator(step, resolve)
    if locator and any(
        element_is_usable(element, require_hit_target=False)
        and locator_match_score(locator, element) > 0
        for element in observation.elements
        if isinstance(element, dict)
    ):
        return SuccessorState.PRESENT_NOT_READY
    return SuccessorState.ABSENT


def _resolved_locator(
    step: CachedWorkflowStep,
    resolve: Callable[[CachedParameterBinding], object | None],
) -> dict:
    locator = dict(step.locator or {})
    for key, binding in step.locator_bindings.items():
        value = resolve(binding)
        if value is None:
            return {}
        locator[key] = str(value)
    return locator


def _exact_label(element: object, text: str) -> bool:
    if not isinstance(element, dict):
        return False
    wanted = _normalize(text)
    return wanted in {
        _normalize(element.get("name")),
        _normalize(element.get("text")),
        _normalize(element.get("placeholder")),
    }


def _normalize(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


__all__ = ["SuccessorState", "classify_successor"]
