"""State-aware observation policies for the browser agent loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation, StepRecord
from app.enterprise_capabilities.browser.engine.observation_freshness import observation_fingerprint


READ_ONLY_TOOLS = frozenset({
    "browser_read_text",
    "browser_screenshot",
    "browser_observe",
})

POST_ACTION_MUTATIONS = frozenset({
    "browser_click",
    "browser_click_at",
    "browser_fill",
    "browser_type_at",
    "browser_select",
    "browser_press",
    "browser_upload_file",
    "browser_paste_image",
})


@dataclass(frozen=True)
class PostActionObservationCheck:
    required: bool
    last_mutation_index: int = -1
    last_fresh_index: int = -1


def post_action_observation_check(
    history: Sequence[StepRecord],
) -> PostActionObservationCheck:
    """Require another read only when the last action lacks a fresh snapshot.

    Local-agent actions that return a post-action DOM store that fresh
    observation on the action's own StepRecord. Older agents and fill calls
    without an observation remain protected by the explicit re-read barrier.
    """
    last_mutation = -1
    for index, record in enumerate(history):
        if str(record.decision.tool or "") in POST_ACTION_MUTATIONS:
            last_mutation = index
    if last_mutation < 0:
        return PostActionObservationCheck(required=False)

    last_fresh = -1
    for index in range(last_mutation, len(history)):
        observation = history[index].observation
        if observation.fresh and bool(observation.revision):
            last_fresh = index
    return PostActionObservationCheck(
        required=last_fresh < last_mutation,
        last_mutation_index=last_mutation,
        last_fresh_index=last_fresh,
    )


def read_count_for_current_state(
    history: Iterable[StepRecord],
    current: Observation,
) -> int:
    """Count successful reads of this concrete state, not every state on URL."""
    current_key = observation_state_key(current)
    if not current_key[0] or not current_key[1]:
        return 0
    return sum(
        1
        for record in history
        if record.ok
        and str(record.decision.tool or "") in READ_ONLY_TOOLS
        and observation_state_key(record.observation) == current_key
    )


def observation_state_key(observation: Observation) -> tuple[str, str]:
    url = str(observation.url or "").strip()
    fingerprint = str(observation.state_fingerprint or "").strip()
    if not fingerprint and observation.fresh:
        fingerprint = observation_fingerprint(
            url=observation.url,
            title=observation.title,
            page_text=observation.page_text,
            elements=observation.elements,
        )
    return url, fingerprint


__all__ = [
    "POST_ACTION_MUTATIONS",
    "READ_ONLY_TOOLS",
    "PostActionObservationCheck",
    "observation_state_key",
    "post_action_observation_check",
    "read_count_for_current_state",
]
