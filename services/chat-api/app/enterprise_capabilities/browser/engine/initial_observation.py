"""Initial browser-state acquisition for a desktop browser node."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation

from app.enterprise_capabilities.browser.engine.observation_freshness import adopt_probed_observation


Dispatch = Callable[
    [Decision],
    Awaitable[tuple[Any, bool, str | None]],
]
ObservationParser = Callable[[Any], Observation | None]


@dataclass(frozen=True)
class InitialObservationResult:
    observation: Observation
    adopted: bool
    attempts: int
    error: str = ""


async def acquire_initial_observation(
    current: Observation,
    *,
    dispatch: Dispatch,
    parse_observation: ObservationParser,
    max_attempts: int = 2,
    retry_delay_seconds: float = 0.15,
) -> InitialObservationResult:
    """Read the active tab, retrying one safe read-only attach race.

    A failed probe must not be mistaken for an empty browser. The caller can
    still fall back to its normal freshness barrier after both attempts fail.
    """
    attempts = max(1, int(max_attempts))
    last_error = ""
    for attempt in range(1, attempts + 1):
        try:
            payload, ok, error = await dispatch(Decision(
                tool="browser_observe",
                args={},
                rationale="cross-node state handoff probe",
            ))
        except Exception as exc:
            payload, ok, error = None, False, f"probe-exception: {exc}"

        if ok:
            try:
                probed = parse_observation(payload)
                adopted = adopt_probed_observation(current, probed)
            except Exception as exc:
                probed = None
                adopted = current
                last_error = f"probe-parse-error: {exc}"
            if adopted is not current:
                return InitialObservationResult(
                    observation=adopted,
                    adopted=True,
                    attempts=attempt,
                )
            if probed is None and not last_error:
                last_error = "probe returned no concrete page observation"
        else:
            last_error = str(error or "initial browser observation failed")

        if attempt < attempts and retry_delay_seconds > 0:
            await asyncio.sleep(retry_delay_seconds)

    return InitialObservationResult(
        observation=current,
        adopted=False,
        attempts=attempts,
        error=last_error,
    )


__all__ = ["InitialObservationResult", "acquire_initial_observation"]
