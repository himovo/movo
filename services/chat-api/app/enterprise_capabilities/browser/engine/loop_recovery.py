"""Deterministic recovery decisions for exhausted browser-loop guards."""

from __future__ import annotations

from typing import Sequence

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation, StepRecord

from .loop_observation_policy import observation_state_key


_READ_BUDGET_ERROR = "read-budget exhausted on "


def recovery_decision_after_guard_failure(
    history: Sequence[StepRecord],
    current: Observation,
    *,
    lang: str,
) -> Decision | None:
    """Stop re-planning after a deterministic guard already rejected a turn.

    Feeding the same guard error to the model several more times cannot reveal
    new DOM evidence.  Suspend once and let a human clarify the hidden target
    or change the page, while preserving the browser checkpoint for resume.
    """
    if not history:
        return None
    latest = history[-1]
    if not str(latest.error or "").startswith(_READ_BUDGET_ERROR):
        return None
    if observation_state_key(latest.observation) != observation_state_key(current):
        return None
    question = (
        "当前页面状态已经读取到上限，但仍没有得到可执行的新目标。请确认页面上下一步应点击的位置，"
        "或手动将页面调整到下一步后交回控制。"
        if lang.startswith("zh") else
        "This page state reached its read limit without yielding a new actionable target. "
        "Please identify the next control or move the page to the next state, then return control."
    )
    return Decision(
        tool="browser_ask_user",
        args={"question": question},
        rationale="deterministic recovery after read-budget exhaustion",
    )


__all__ = ["recovery_decision_after_guard_failure"]
