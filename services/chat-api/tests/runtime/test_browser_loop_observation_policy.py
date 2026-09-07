from app.enterprise_capabilities.browser.engine.loop_observation_policy import (
    is_technical_recovery_observation,
    observe_count_for_current_interaction_state,
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


def _recovery_step(observation: Observation) -> StepRecord:
    return StepRecord(
        observation=observation,
        decision=Decision(
            tool="browser_observe",
            args={},
            rationale="click target changed during dispatch; refresh DOM before resolving another target",
        ),
        ok=True,
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


def test_technical_recovery_observe_does_not_consume_read_budgets() -> None:
    observation = _obs(state="results")
    history = [_recovery_step(observation)]

    assert is_technical_recovery_observation(history[0].decision) is True
    assert read_count_for_current_state(history, observation) == 0
    assert observe_count_for_current_interaction_state(history, observation) == 0


def test_observe_budget_ignores_dynamic_text_when_controls_are_unchanged() -> None:
    first = _obs(state="comment-entry")
    first.page_text = "播放进度 01:00"
    first.state_fingerprint = "dynamic:first"
    second = _obs(state="comment-entry")
    second.page_text = "播放进度 01:01"
    second.state_fingerprint = "dynamic:second"

    assert observe_count_for_current_interaction_state(
        [_step("browser_observe", first)], second,
    ) == 1


def test_observe_budget_resets_when_editor_becomes_editable() -> None:
    closed = _obs(state="说点什么...")
    opened = _obs(state="说点什么...")
    opened.elements[0] = {
        "ref": "e2", "role": "textbox", "name": "说点什么...",
        "editable": True, "visible": True,
    }

    assert observe_count_for_current_interaction_state(
        [_step("browser_observe", closed)], opened,
    ) == 0
