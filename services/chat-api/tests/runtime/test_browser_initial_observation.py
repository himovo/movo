from __future__ import annotations

import asyncio

from app.enterprise_capabilities.browser.engine.initial_observation import acquire_initial_observation
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


def _observation(url: str, *, fresh: bool) -> Observation:
    return Observation(
        url=url,
        title="",
        elements=[],
        revision="state:1" if fresh else "",
        state_fingerprint="fingerprint" if fresh else "",
        fresh=fresh,
    )


def test_initial_observation_retries_a_read_only_attach_failure() -> None:
    current = _observation("about:blank", fresh=False)
    probed = _observation("https://example.test", fresh=True)
    calls = 0

    async def dispatch(_decision):
        nonlocal calls
        calls += 1
        if calls == 1:
            return None, False, "dispatch-error: target is attaching"
        return {"url": probed.url}, True, None

    def parse(payload):
        if not isinstance(payload, dict):
            return None
        return _observation(str(payload.get("url") or ""), fresh=True)

    result = asyncio.run(acquire_initial_observation(
        current,
        dispatch=dispatch,
        parse_observation=parse,
        retry_delay_seconds=0,
    ))

    assert result.adopted is True
    assert result.attempts == 2
    assert result.observation.url == "https://example.test"
    assert calls == 2


def test_initial_observation_returns_original_state_after_bounded_failures() -> None:
    current = _observation("about:blank", fresh=False)

    async def dispatch(_decision):
        return None, False, "agent-disconnected"

    result = asyncio.run(acquire_initial_observation(
        current,
        dispatch=dispatch,
        parse_observation=lambda _payload: None,
        retry_delay_seconds=0,
    ))

    assert result.adopted is False
    assert result.attempts == 2
    assert result.observation is current
    assert result.error == "agent-disconnected"


def test_initial_observation_retries_a_malformed_payload() -> None:
    current = _observation("about:blank", fresh=False)
    calls = 0

    async def dispatch(_decision):
        nonlocal calls
        calls += 1
        return {"url": "https://example.test"}, True, None

    def parse(_payload):
        if calls == 1:
            raise ValueError("malformed frame count")
        return _observation("https://example.test", fresh=True)

    result = asyncio.run(acquire_initial_observation(
        current,
        dispatch=dispatch,
        parse_observation=parse,
        retry_delay_seconds=0,
    ))

    assert result.adopted is True
    assert result.attempts == 2
    assert calls == 2
