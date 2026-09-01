from app.enterprise_capabilities.browser.engine.visual_observation_guard import (
    REDUNDANT_VISUAL_OBSERVATION,
    redundant_visual_observation,
)
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import (
    Decision,
    Observation,
    StepRecord,
)


def _observation(*, screenshot: str | None = "image") -> Observation:
    return Observation(
        url="https://example.test/results",
        title="Results",
        elements=[],
        revision="tab:4",
        state_fingerprint="stable-page",
        fresh=True,
        screenshot=screenshot,
    )


def _visual_observe() -> Decision:
    return Decision(
        tool="browser_observe",
        args={"with_screenshot": True},
    )


def test_blocks_immediate_visual_observation_on_same_state() -> None:
    observation = _observation()
    previous = StepRecord(
        observation=observation,
        decision=_visual_observe(),
        ok=True,
    )

    result = redundant_visual_observation(
        _visual_observe(),
        current=observation,
        history=[previous],
    )

    assert result.blocked is True
    assert REDUNDANT_VISUAL_OBSERVATION in result.reason


def test_allows_visual_observation_after_an_intervening_action() -> None:
    observation = _observation()
    history = [
        StepRecord(
            observation=observation,
            decision=_visual_observe(),
            ok=True,
        ),
        StepRecord(
            observation=observation,
            decision=Decision(tool="browser_scroll", args={"delta_y": 500}),
            ok=True,
        ),
    ]

    result = redundant_visual_observation(
        _visual_observe(),
        current=observation,
        history=history,
    )

    assert result.blocked is False


def test_blocks_when_executor_reuses_the_exact_latest_snapshot() -> None:
    observation = _observation()
    observation.state_fingerprint = ""
    previous = StepRecord(
        observation=observation,
        decision=_visual_observe(),
        ok=True,
    )

    result = redundant_visual_observation(
        _visual_observe(),
        current=observation,
        history=[previous],
    )

    assert result.blocked is True


def test_allows_different_capture_scope_or_missing_screenshot() -> None:
    observation = _observation()
    previous = StepRecord(
        observation=observation,
        decision=_visual_observe(),
        ok=True,
    )

    full_page = redundant_visual_observation(
        Decision(tool="browser_screenshot", args={"full_page": True}),
        current=observation,
        history=[previous],
    )
    missing = redundant_visual_observation(
        _visual_observe(),
        current=_observation(screenshot=None),
        history=[previous],
    )

    assert full_page.blocked is False
    assert missing.blocked is False


def test_allows_one_retry_after_reuse_feedback() -> None:
    observation = _observation()
    rejected = StepRecord(
        observation=observation,
        decision=_visual_observe(),
        ok=False,
        error=f"{REDUNDANT_VISUAL_OBSERVATION}: reuse it",
    )

    result = redundant_visual_observation(
        _visual_observe(),
        current=observation,
        history=[rejected],
    )

    assert result.blocked is False
