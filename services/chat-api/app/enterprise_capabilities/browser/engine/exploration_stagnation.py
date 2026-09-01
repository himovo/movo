"""Bound repeated exploratory actions by observed browser-state progress."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping, Sequence

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation, StepRecord
from app.enterprise_capabilities.browser.engine.loop_observation_policy import READ_ONLY_TOOLS, observation_state_key


@dataclass(frozen=True)
class ExplorationStagnation:
    blocked: bool
    repeated_outcomes: int = 0
    reason: str = ""


def assess_exploration_stagnation(
    decision: Decision,
    history: Sequence[StepRecord],
    current: Observation,
    *,
    maximum_same_outcomes: int = 3,
) -> ExplorationStagnation:
    action_key = exploration_action_key(decision)
    if action_key is None:
        return ExplorationStagnation(blocked=False)

    current_signature = exploration_state_signature(current)
    repeated = 0
    for record in reversed(history):
        record_signature = exploration_state_signature(record.observation)
        record_key = exploration_action_key(record.decision)
        if str(record.decision.tool or "") in READ_ONLY_TOOLS and record_signature == current_signature:
            continue
        if record_key != action_key or record_signature != current_signature:
            break
        if not record.ok:
            if str(record.error or "").startswith("exploration action "):
                repeated += 1
                continue
            break
        repeated += 1

    if repeated < max(1, maximum_same_outcomes):
        return ExplorationStagnation(blocked=False, repeated_outcomes=repeated)
    return ExplorationStagnation(
        blocked=True,
        repeated_outcomes=repeated,
        reason=(
            f"exploration action {action_key} produced the same page/viewport state "
            f"{repeated} times; choose a different target or strategy"
        ),
    )


def exploration_action_key(decision: Decision) -> tuple[str, ...] | None:
    tool = str(decision.tool or "")
    args = dict(decision.args or {})
    if tool == "browser_scroll":
        return (
            tool,
            str(args.get("direction") or "").strip().lower(),
            str(args.get("ref") or "").strip(),
        )
    if tool == "browser_wait_for" and not str(args.get("text") or "").strip() and not str(args.get("ref") or "").strip():
        return (tool, "delay")
    return None


def exploration_state_signature(observation: Observation) -> str:
    viewport = dict(observation.viewport or {})
    scroll = _scroll_position(observation.diagnostics)
    visible = []
    for element in list(observation.elements or []):
        if not isinstance(element, Mapping) or element.get("inViewport") is not True:
            continue
        visible.append((
            str(element.get("role") or ""),
            str(element.get("name") or element.get("text") or "")[:120],
            str(element.get("scopeId") or ""),
        ))
        if len(visible) >= 60:
            break
    payload = {
        "state": observation_state_key(observation),
        "viewport": (
            _bucket(viewport.get("scrollX")),
            _bucket(viewport.get("scrollY")),
        ),
        "nested_scroll": scroll,
        "visible": visible,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _scroll_position(diagnostics: Any) -> tuple[str, int, int] | None:
    if not isinstance(diagnostics, Mapping):
        return None
    scroll = diagnostics.get("scroll")
    if not isinstance(scroll, Mapping):
        return None
    after = scroll.get("after")
    if not isinstance(after, Mapping):
        return None
    return (
        str(after.get("identity") or after.get("kind") or ""),
        _bucket(after.get("top")),
        _bucket(after.get("maximum")),
    )


def _bucket(value: Any, size: int = 40) -> int:
    try:
        return int(float(value or 0) // size)
    except (TypeError, ValueError):
        return 0


__all__ = [
    "ExplorationStagnation",
    "assess_exploration_stagnation",
    "exploration_action_key",
    "exploration_state_signature",
]
