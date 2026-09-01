from __future__ import annotations

from typing import Any, Callable

from app.enterprise_capabilities.browser.engine.action_target import locator_matches
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation

from .contracts import CachedParameterBinding, CachedWorkflowStep
from .page_state import same_url_shape
from .target_state import (
    actionable_surface_identity,
    element_is_usable,
    logical_action_succeeded,
)


_VERIFIED_VALUE_TOOLS = frozenset({
    # These actions are already verified by the native-CDP sidecar before it
    # returns ok. Requiring a whole-page fingerprint as a second proof creates
    # false failures for controls whose value/media state is not in the scan.
    "browser_fill",
    "browser_type_at",
    "browser_upload_file",
    "browser_paste_image",
})

_RESULT_VERIFIED_TOOLS = frozenset({"browser_select", "browser_scroll", "browser_wait_for"})

_INTERACTION_TOOLS = frozenset({
    "browser_click",
    "browser_click_at",
    "browser_hover",
    "browser_press",
})

_NAVIGATION_TOOLS = frozenset({
    "browser_navigate",
    "browser_tab_new",
    "browser_back",
    "browser_forward",
})

_POSITIVE_TRANSITIONS = frozenset({
    "new_interaction_surface",
})

SUPPORTED_REPLAY_EVIDENCE_TOOLS = frozenset(
    _VERIFIED_VALUE_TOOLS | _RESULT_VERIFIED_TOOLS | _INTERACTION_TOOLS | _NAVIGATION_TOOLS
)


def replay_postcondition_satisfied(
    step: CachedWorkflowStep,
    *,
    before: Observation | None,
    after: Observation,
    resolve: Callable[[CachedParameterBinding], object | None],
    successor: CachedWorkflowStep | None = None,
    allow_deferred_completion: bool = False,
    result: Any = None,
) -> bool:
    """Evaluate portable completion evidence for one successfully dispatched action."""

    if not _target_route_matches(step, after):
        return False
    tool = str(step.tool or "")
    if tool not in SUPPORTED_REPLAY_EVIDENCE_TOOLS:
        return False
    if tool in _VERIFIED_VALUE_TOOLS:
        return True
    if tool in _RESULT_VERIFIED_TOOLS:
        return logical_action_succeeded(tool, result, after.diagnostics)
    if tool in _NAVIGATION_TOOLS:
        return _navigation_satisfied(step, before, after)
    if tool not in _INTERACTION_TOOLS:
        return not step.expect_state_change or _generic_progress(before, after)
    if successor is not None and cached_target_is_ready(
        successor, after, resolve, before=before,
    ):
        return True
    if _disclosure_is_expanded(step, after):
        return True
    if _interaction_transition(after) in _POSITIVE_TRANSITIONS and _new_actionable_surface(before, after):
        return True
    if not step.expect_state_change:
        return True
    # A non-idempotent terminal click was delivered to a verified live target.
    # Do not retry it merely because the page has not rendered a receipt yet;
    # advance to the existing business-effect completion guard, which is the
    # authoritative place to confirm or reject the write.
    if allow_deferred_completion:
        return True
    return _generic_progress(before, after)


def cached_target_is_ready(
    step: CachedWorkflowStep,
    observation: Observation,
    resolve: Callable[[CachedParameterBinding], object | None],
    *,
    before: Observation | None = None,
) -> bool:
    """Return whether a successor's semantic target is already visible."""

    if step.tool == "browser_wait_for":
        text = resolved_wait_text(step, resolve)
        if not text:
            return False
        if observation_contains_text(observation, text, actionable=True):
            return True
        return bool(
            before is not None
            and not observation_contains_text(before, text)
            and observation_contains_text(observation, text)
        )
    locator = _resolved_locator(step, resolve)
    if not locator:
        return False
    return any(
        locator_matches(locator, element, tool=step.tool)
        for element in observation.elements
    )


def resolved_wait_text(
    step: CachedWorkflowStep,
    resolve: Callable[[CachedParameterBinding], object | None],
) -> str:
    text = str(step.args.get("text") or "").strip()
    if text:
        return text
    binding = step.arg_bindings.get("text")
    value = resolve(binding) if binding is not None else None
    return str(value or "").strip()


def observation_contains_text(
    observation: Observation,
    text: str,
    *,
    actionable: bool = False,
) -> bool:
    wanted = _normalize(text)
    if not wanted:
        return False
    if not actionable and wanted in _normalize(observation.page_text):
        return True
    return any(
        wanted in _normalize(element.get(key))
        for element in observation.elements
        if element_is_usable(element, require_hit_target=actionable)
        for key in ("name", "text", "placeholder", "description")
    )


def _target_route_matches(step: CachedWorkflowStep, after: Observation) -> bool:
    return not (
        step.target_url_shape
        and step.target_url_shape != step.source_url_shape
        and not same_url_shape(after.url, step.target_url_shape)
    )


def _navigation_satisfied(
    step: CachedWorkflowStep,
    before: Observation | None,
    after: Observation,
) -> bool:
    if step.target_url_shape:
        return same_url_shape(after.url, step.target_url_shape)
    return before is None or before.url != after.url or not step.expect_state_change


def _generic_progress(before: Observation | None, after: Observation) -> bool:
    if before is None or before.url != after.url:
        return True
    transition = _interaction_transition(after)
    if transition in _POSITIVE_TRANSITIONS and _new_actionable_surface(before, after):
        return True
    return False


def _new_actionable_surface(before: Observation | None, after: Observation) -> bool:
    previous = {
        actionable_surface_identity(element)
        for element in (before.elements if before is not None else [])
        if element_is_usable(element)
    }
    return any(
        element_is_usable(element)
        and actionable_surface_identity(element) not in previous
        for element in after.elements
    )


def _interaction_transition(observation: Observation) -> str:
    dom_diff = observation.dom_diff if isinstance(observation.dom_diff, dict) else {}
    transition = str(dom_diff.get("transition") or "").strip().casefold()
    if transition:
        return transition
    diagnostics = observation.diagnostics if isinstance(observation.diagnostics, dict) else {}
    action = diagnostics.get("action") if isinstance(diagnostics.get("action"), dict) else {}
    stability = action.get("stability") if isinstance(action.get("stability"), dict) else {}
    return str(stability.get("transition") or "").strip().casefold()


def _disclosure_is_expanded(step: CachedWorkflowStep, after: Observation) -> bool:
    locator = dict(step.locator or {})
    is_disclosure = bool(
        locator.get("hasPopup")
        or str(locator.get("semanticPurpose") or "").casefold() == "navigation-expand"
    )
    if not is_disclosure:
        return False
    for element in after.elements:
        if locator_matches(locator, element, tool=step.tool) and element.get("expanded") is True:
            return True
    dom_diff = after.dom_diff if isinstance(after.dom_diff, dict) else {}
    changed = dom_diff.get("changed_elements")
    return any(
        isinstance(element, dict) and element.get("expanded") is True
        for element in (changed if isinstance(changed, list) else [])
    )


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


def _normalize(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


__all__ = [
    "cached_target_is_ready",
    "observation_contains_text",
    "replay_postcondition_satisfied",
    "resolved_wait_text",
    "SUPPORTED_REPLAY_EVIDENCE_TOOLS",
]
