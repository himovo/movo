from __future__ import annotations

from app.enterprise_capabilities.browser.engine.loop_recovery import recovery_decision_after_guard_failure
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation, StepRecord


def _obs(fingerprint: str) -> Observation:
    return Observation(
        url="https://example.test/list",
        title="List",
        elements=[{"ref": "e1", "role": "button", "name": "Open"}],
        fresh=True,
        state_fingerprint=fingerprint,
    )


def test_read_budget_failure_forces_intervention_without_another_model_turn() -> None:
    observation = _obs("same-state")
    history = [StepRecord(
        observation=observation,
        decision=Decision(tool="browser_observe", args={}, rationale="read again"),
        ok=False,
        error="read-budget exhausted on https://example.test/list",
    )]

    decision = recovery_decision_after_guard_failure(history, observation, lang="zh")

    assert decision is not None
    assert decision.tool == "browser_ask_user"
    assert "读取到上限" in str(decision.args.get("question"))


def test_recovery_does_not_follow_the_guard_to_a_new_page_state() -> None:
    history = [StepRecord(
        observation=_obs("old-state"),
        decision=Decision(tool="browser_observe", args={}, rationale="read again"),
        ok=False,
        error="read-budget exhausted on https://example.test/list",
    )]

    assert recovery_decision_after_guard_failure(history, _obs("new-state"), lang="zh") is None


def test_unrelated_failure_keeps_normal_planning_available() -> None:
    observation = _obs("same-state")
    history = [StepRecord(
        observation=observation,
        decision=Decision(tool="browser_click", args={"ref": "e1"}, rationale="open"),
        ok=False,
        error="target moved",
    )]

    assert recovery_decision_after_guard_failure(history, observation, lang="zh") is None
