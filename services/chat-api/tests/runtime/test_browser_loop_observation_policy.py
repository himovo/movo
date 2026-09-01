from app.enterprise_capabilities.browser.engine.loop_observation_policy import (
    post_action_observation_check,
    read_count_for_current_state,
)
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation, StepRecord


def _obs(*, state: str, fresh: bool = True) -> Observation:
    return Observation(
        url="https://example.test/app",
        title="App",
        elements=[{"ref": "e1", "role": "button", "name": state}],
        page_text=state,
        revision=f"revision:{state}" if fresh else "",
        state_fingerprint=f"state:{state}" if fresh else "",
        fresh=fresh,
    )


def _step(tool: str, observation: Observation, *, ok: bool = True) -> StepRecord:
    return StepRecord(
        observation=observation,
        decision=Decision(tool=tool, args={}),
        ok=ok,
    )


def test_fresh_snapshot_returned_by_action_satisfies_done_check() -> None:
    check = post_action_observation_check([
        _step("browser_click", _obs(state="menu-open")),
    ])
    assert check.required is False


def test_action_without_snapshot_still_requires_explicit_observation() -> None:
    history = [_step("browser_fill", _obs(state="", fresh=False))]
    assert post_action_observation_check(history).required is True

    history.append(_step("browser_observe", _obs(state="filled")))
    assert post_action_observation_check(history).required is False


def test_read_budget_resets_when_same_url_has_new_state() -> None:
    history = [
        _step("browser_observe", _obs(state="closed")),
        _step("browser_read_text", _obs(state="closed")),
        _step("browser_screenshot", _obs(state="closed")),
    ]
    assert read_count_for_current_state(history, _obs(state="closed")) == 3
    assert read_count_for_current_state(history, _obs(state="menu-open")) == 0


def test_failed_reads_do_not_consume_successful_read_budget() -> None:
    history = [_step("browser_observe", _obs(state="closed"), ok=False)]
    assert read_count_for_current_state(history, _obs(state="closed")) == 0
