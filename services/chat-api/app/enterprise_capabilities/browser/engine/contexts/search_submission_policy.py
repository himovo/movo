"""Bounded, site-independent submission policy for a filled search field."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from app.enterprise_capabilities.browser.engine.effect_verification.interaction_relation import (
    resolve_field_action_relation,
)
from app.enterprise_capabilities.browser.engine.form_input.identity import find_field
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


_IDLE = "idle"
_PRESS_ENTER = "press_enter"
_REFRESH_FIELD = "refresh_field"
_OBSERVE_ENTER = "observe_enter"
_CLICK_SUBMIT = "click_submit"
_OBSERVE_CLICK = "observe_click"
_EXHAUSTED = "exhausted"


@dataclass
class SearchSubmissionState:
    """Durable state for one filled search query.

    The policy has a strict, bounded order: press Enter on the live field,
    observe, click one structurally related search control, observe, then
    release action selection back to the planner.
    """

    query: str = ""
    field_target: Dict[str, Any] = field(default_factory=dict)
    phase: str = _IDLE
    field_refreshes: int = 0
    enter_attempts: int = 0
    button_attempts: int = 0

    @property
    def active(self) -> bool:
        return bool(self.query) and self.phase not in {_IDLE, _EXHAUSTED}

    def as_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "phase": self.phase,
            "enter_attempts": self.enter_attempts,
            "button_attempts": self.button_attempts,
        }


def begin_search_submission(
    state: SearchSubmissionState,
    *,
    query: str,
    field_target: Dict[str, Any],
) -> None:
    normalized = str(query or "").strip()
    if not normalized or not field_target:
        return
    state.query = normalized
    state.field_target = dict(field_target)
    state.phase = _PRESS_ENTER
    state.field_refreshes = 0
    state.enter_attempts = 0
    state.button_attempts = 0


def record_search_submission_transition(
    state: SearchSubmissionState,
    decision: Decision,
    observation: Observation,
    *,
    search_confirmed: bool,
) -> None:
    if search_confirmed:
        clear_search_submission(state)
        return
    if not state.active:
        return

    tool = str(decision.tool or "")
    key = str((decision.args or {}).get("key") or "").strip().casefold()
    if (
        state.phase == _PRESS_ENTER
        and tool == "browser_press"
        and key in {"enter", "return"}
    ):
        state.enter_attempts += 1
        state.phase = _OBSERVE_ENTER
        return
    if state.phase == _REFRESH_FIELD and tool == "browser_observe":
        state.phase = (
            _PRESS_ENTER
            if _live_search_field(state, observation) is not None
            else _EXHAUSTED
        )
        return
    if state.phase == _OBSERVE_ENTER and tool == "browser_observe":
        state.phase = _CLICK_SUBMIT
        return
    if state.phase == _CLICK_SUBMIT and tool == "browser_click":
        state.button_attempts += 1
        state.phase = _OBSERVE_CLICK
        return
    if state.phase == _OBSERVE_CLICK and tool == "browser_observe":
        state.phase = _EXHAUSTED


def suggest_search_submission_action(
    state: SearchSubmissionState,
    observation: Observation,
) -> Optional[Decision]:
    if not state.active:
        return None
    if state.phase == _PRESS_ENTER:
        field = _live_search_field(state, observation)
        if field is None:
            if state.field_refreshes >= 1:
                state.phase = _EXHAUSTED
                return None
            state.field_refreshes += 1
            state.phase = _REFRESH_FIELD
            return Decision(
                tool="browser_observe",
                args={},
                rationale="refresh the DOM before submitting the confirmed search field",
            )
        return Decision(
            tool="browser_press",
            args={"key": "Enter", "ref": str(field.get("ref") or "")},
            rationale="submit the confirmed search query from its live field",
        )
    if state.phase in {_OBSERVE_ENTER, _OBSERVE_CLICK}:
        return Decision(
            tool="browser_observe",
            args={},
            rationale="verify whether the bounded search submission advanced the page",
        )
    if state.phase == _CLICK_SUBMIT:
        field = _live_search_field(state, observation)
        action = _unique_related_search_action(field, observation)
        if action is None:
            state.phase = _EXHAUSTED
            return None
        return Decision(
            tool="browser_click",
            args={"ref": str(action.get("ref") or "")},
            rationale="click the current search control structurally bound to the filled field",
        )
    return None


def clear_search_submission(state: SearchSubmissionState) -> None:
    state.query = ""
    state.field_target = {}
    state.phase = _IDLE
    state.field_refreshes = 0
    state.enter_attempts = 0
    state.button_attempts = 0


def _live_search_field(
    state: SearchSubmissionState,
    observation: Observation,
) -> Optional[Dict[str, Any]]:
    field = find_field(
        observation.elements,
        state.field_target,
        fallback_ref=str(state.field_target.get("ref") or ""),
    )
    if field is None:
        query = _normalized_value(state.query)
        candidates = [
            item
            for item in observation.elements
            if isinstance(item, dict)
            and item.get("editable") is True
            and _is_search_candidate(item)
            and _normalized_value(item.get("value")) == query
        ]
        field = candidates[0] if len(candidates) == 1 else None
    if not isinstance(field, dict):
        return None
    if field.get("visible") is False or field.get("disabled") is True:
        return None
    if not field.get("editable"):
        return None
    return field


def _is_search_candidate(item: Dict[str, Any]) -> bool:
    return (
        str(item.get("semanticPurpose") or "").strip().casefold() == "search"
        or bool(item.get("searchContext"))
        or str(item.get("role") or "").strip().casefold() == "searchbox"
        or str(item.get("scopeRole") or "").strip().casefold() == "search"
        or str(item.get("formOwnerRole") or "").strip().casefold() == "search"
    )


def _normalized_value(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _unique_related_search_action(
    field: Optional[Dict[str, Any]],
    observation: Observation,
) -> Optional[Dict[str, Any]]:
    if field is None:
        return None
    ranked: list[tuple[int, Dict[str, Any]]] = []
    semantic_fallbacks: list[tuple[int, Dict[str, Any]]] = []
    for item in observation.elements:
        if not isinstance(item, dict):
            continue
        if (
            item.get("visible") is False
            or item.get("disabled") is True
            or item.get("editable") is True
            or not str(item.get("ref") or "").strip()
        ):
            continue
        rank = _search_action_rank(item)
        if not rank:
            continue
        semantic_fallbacks.append((rank, item))
        if not resolve_field_action_relation(field, item).related:
            continue
        ranked.append((rank, item))
    if not ranked:
        # Some public search pages expose the input and submit control without
        # form-owner metadata. A single, explicitly search-semantic control is
        # still a bounded target; ambiguity remains fail-closed.
        strongest = max((rank for rank, _ in semantic_fallbacks), default=0)
        best_fallbacks = [item for rank, item in semantic_fallbacks if rank == strongest]
        return best_fallbacks[0] if strongest >= 2 and len(best_fallbacks) == 1 else None
    best_rank = max(rank for rank, _ in ranked)
    best = [item for rank, item in ranked if rank == best_rank]
    return best[0] if len(best) == 1 else None


def _search_action_rank(item: Dict[str, Any]) -> int:
    if str(item.get("semanticPurpose") or "").strip().casefold() == "search":
        return 3
    if str(item.get("type") or "").strip().casefold() == "submit":
        return 2
    role = str(item.get("role") or "").strip().casefold()
    if item.get("searchContext") and role in {"button", "menuitem"}:
        return 1
    return 0


__all__ = [
    "SearchSubmissionState",
    "begin_search_submission",
    "clear_search_submission",
    "record_search_submission_transition",
    "suggest_search_submission_action",
]
