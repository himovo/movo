from app.enterprise_capabilities.browser.engine.exploration_stagnation import assess_exploration_stagnation
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation, StepRecord


def _obs(*, top: int, state: str = "same", nested_top: int | None = None) -> Observation:
    diagnostics = None
    if nested_top is not None:
        diagnostics = {
            "scroll": {
                "after": {"kind": "element", "identity": "#menu", "top": nested_top, "maximum": 800},
            },
        }
    return Observation(
        url="https://example.test/app",
        title="App",
        elements=[],
        page_text=state,
        state_fingerprint=f"state:{state}",
        revision=f"revision:{state}",
        fresh=True,
        viewport={"scrollX": 0, "scrollY": top},
        diagnostics=diagnostics,
    )


def _decision(tool: str = "browser_scroll", **args) -> Decision:
    return Decision(tool=tool, args=args or {"direction": "down"})


def _record(decision: Decision, observation: Observation) -> StepRecord:
    return StepRecord(observation=observation, decision=decision, ok=True)


def test_repeated_scroll_is_blocked_only_after_same_viewport_outcome() -> None:
    decision = _decision()
    history = [_record(decision, _obs(top=1200)) for _ in range(3)]
    result = assess_exploration_stagnation(decision, history, _obs(top=1200))
    assert result.blocked is True


def test_window_scroll_progress_resets_stagnation() -> None:
    decision = _decision()
    history = [
        _record(decision, _obs(top=400)),
        _record(decision, _obs(top=800)),
        _record(decision, _obs(top=1200)),
    ]
    result = assess_exploration_stagnation(decision, history, _obs(top=1200))
    assert result.blocked is False


def test_nested_scroll_progress_is_not_mistaken_for_stagnation() -> None:
    decision = _decision(ref="menu", direction="down")
    history = [
        _record(decision, _obs(top=0, nested_top=80)),
        _record(decision, _obs(top=0, nested_top=160)),
        _record(decision, _obs(top=0, nested_top=240)),
    ]
    result = assess_exploration_stagnation(decision, history, _obs(top=0, nested_top=240))
    assert result.blocked is False


def test_delay_wait_is_bounded_but_condition_wait_is_not() -> None:
    delay = _decision("browser_wait_for", timeout=1000)
    history = [_record(delay, _obs(top=0)) for _ in range(3)]
    assert assess_exploration_stagnation(delay, history, _obs(top=0)).blocked is True

    condition = _decision("browser_wait_for", text="完成", timeout=1000)
    assert assess_exploration_stagnation(condition, history, _obs(top=0)).blocked is False


def test_repeating_a_policy_block_does_not_reset_the_guard() -> None:
    decision = _decision()
    observation = _obs(top=1200)
    history = [_record(decision, observation) for _ in range(3)]
    history.append(StepRecord(
        observation=observation,
        decision=decision,
        ok=False,
        error="exploration action ('browser_scroll', 'down', '') produced the same state",
    ))
    assert assess_exploration_stagnation(decision, history, observation).blocked is True
