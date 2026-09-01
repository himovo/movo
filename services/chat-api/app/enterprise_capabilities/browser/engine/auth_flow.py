"""Passive authentication wait loop for desktop browser sessions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, Optional, Tuple

from app.enterprise_capabilities.browser.engine.auth_state import AuthTransitionTracker, assessment_from_payload
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


Dispatch = Callable[[Decision], Awaitable[Tuple[Any, bool, Optional[str]]]]
ObservationParser = Callable[[Any], Optional[Observation]]


@dataclass(frozen=True)
class AuthWaitEvent:
    state: str
    observation: Optional[Observation] = None
    url: str = ""


async def wait_for_authentication(
    *,
    dispatch: Dispatch,
    parse_observation: ObservationParser,
    tracker: AuthTransitionTracker,
    current_observation: Observation,
    timeout_seconds: float = 300,
    poll_seconds: float = 1.25,
    idle_grace_ms: int = 1500,
) -> AsyncIterator[AuthWaitEvent]:
    """Observe auth state without navigating, clicking, typing, or stealing focus."""
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    last_state = ""
    observation = current_observation
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(poll_seconds)
        try:
            result, ok, _error = await dispatch(Decision(
                tool="browser_observe",
                args={},
                rationale="passively observe authentication state",
            ))
        except Exception:
            continue
        if not ok or not isinstance(result, dict):
            continue
        nested = result.get("observation") if isinstance(result.get("observation"), dict) else result
        parsed = parse_observation(nested)
        if parsed is not None:
            observation = parsed
        url = str(nested.get("url") or result.get("url") or observation.url or "")
        transition = tracker.observe(
            url=url,
            assessment=assessment_from_payload(result),
            has_page_evidence=bool(observation.elements or observation.page_text or observation.title),
        )
        if transition == "failed" and last_state != "failed":
            yield AuthWaitEvent(state="failed", observation=observation, url=url)
        last_state = transition
        interaction = nested.get("interaction") if isinstance(nested.get("interaction"), dict) else {}
        human_idle_ms = int(interaction.get("humanIdleMs") or interaction.get("human_idle_ms") or 0)
        if transition == "authenticated" and human_idle_ms >= idle_grace_ms:
            yield AuthWaitEvent(state="authenticated", observation=observation, url=url)
            return
    yield AuthWaitEvent(state="timeout", observation=observation, url=observation.url)
