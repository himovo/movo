from __future__ import annotations

from app.enterprise_capabilities.browser.engine.human_assistance_policy import (
    EXPLORATION_STAGNATION,
    NAVIGATION_TARGET_BLOCKED,
    READ_BUDGET,
    browser_human_assistance,
)
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


def _observation(*, purpose: str = "navigation-expand") -> Observation:
    return Observation(
        url="https://example.test/home",
        title="Home",
        elements=[{
            "ref": "e1",
            "role": "button",
            "name": "展开菜单",
            "semanticPurpose": purpose,
        }],
    )


def test_read_budget_is_safe_for_human_handoff() -> None:
    assistance = browser_human_assistance(
        source=READ_BUDGET,
        observation=_observation(),
        lang="zh",
    )
    assert assistance is not None
    assert "已完成，继续执行" in assistance.question


def test_navigation_disclosure_can_request_human_help() -> None:
    assistance = browser_human_assistance(
        source=NAVIGATION_TARGET_BLOCKED,
        observation=_observation(),
        decision=Decision(tool="browser_click", args={"ref": "e1"}),
        lang="zh",
    )
    assert assistance is not None
    assert "展开菜单" in assistance.question


def test_submit_like_or_unknown_click_is_not_converted() -> None:
    assistance = browser_human_assistance(
        source=NAVIGATION_TARGET_BLOCKED,
        observation=_observation(purpose="submit"),
        decision=Decision(tool="browser_click", args={"ref": "e1"}),
        lang="zh",
    )
    assert assistance is None


def test_only_read_only_exploration_is_convertible() -> None:
    allowed = browser_human_assistance(
        source=EXPLORATION_STAGNATION,
        observation=_observation(),
        decision=Decision(tool="browser_scroll", args={"direction": "down"}),
        lang="zh",
    )
    blocked = browser_human_assistance(
        source=EXPLORATION_STAGNATION,
        observation=_observation(),
        decision=Decision(tool="browser_click", args={"ref": "e1"}),
        lang="zh",
    )
    assert allowed is not None
    assert blocked is None
