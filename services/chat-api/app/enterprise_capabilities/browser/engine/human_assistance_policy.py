"""Conservative policy for recoverable browser human-assistance handoffs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.enterprise_capabilities.browser.engine.recovery_identity import browser_recovery_dedupe_key
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


READ_BUDGET = "read_budget"
EXPLORATION_STAGNATION = "exploration_stagnation"
NAVIGATION_TARGET_BLOCKED = "navigation_target_blocked"
NAVIGATION_STAGNATION = "navigation_stagnation"

_NAVIGATION_PURPOSES = {"navigation-expand", "navigation-group"}


@dataclass(frozen=True)
class BrowserHumanAssistance:
    source: str
    question: str
    dedupe_key: str


def browser_human_assistance(
    *,
    source: str,
    observation: Observation,
    lang: str,
    decision: Decision | None = None,
) -> Optional[BrowserHumanAssistance]:
    """Return a handoff only for a whitelisted, human-recoverable page block.

    Business commits, form submission, contract failures and infrastructure
    errors never enter this policy. Callers must name the guard that exhausted
    its own bounded recovery before asking for assistance.
    """
    zh = str(lang or "").startswith("zh")
    if source == READ_BUDGET:
        question = (
            "当前页面已经多次读取，但仍找不到可靠的下一步。请手动将页面调整到下一步，"
            "或点击你认为正确的控件，完成后点击“已完成，继续执行”。"
            if zh else
            "The page has been read repeatedly without a reliable next step. "
            "Please move it to the next state or click the correct control, then choose Done to continue."
        )
        return _result(source, observation, question)

    if source == EXPLORATION_STAGNATION and _is_read_only_exploration(decision):
        question = (
            "页面在连续滚动或等待后没有变化。请手动调整到能继续操作的位置，"
            "完成后点击“已完成，继续执行”。"
            if zh else
            "The page did not change after repeated scrolling or waiting. "
            "Please move it to an actionable state, then choose Done to continue."
        )
        return _result(source, observation, question)

    if source in {NAVIGATION_TARGET_BLOCKED, NAVIGATION_STAGNATION}:
        target = _navigation_target(decision, observation)
        if target is None:
            return None
        label = str(target.get("name") or target.get("text") or "").strip()
        target_text = f"“{label}”" if label else "当前导航控件"
        question = (
            f"{target_text}未能自动打开或推进页面。请手动点击该导航控件并将页面调整到下一步，"
            "完成后点击“已完成，继续执行”。"
            if zh else
            f"{target_text} could not be opened automatically. Please activate the navigation control "
            "and move the page to the next state, then choose Done to continue."
        )
        return _result(source, observation, question)

    return None


def _result(source: str, observation: Observation, question: str) -> BrowserHumanAssistance:
    return BrowserHumanAssistance(
        source=source,
        question=question,
        dedupe_key=browser_recovery_dedupe_key(
            observation,
            family="interaction",
        ),
    )


def _is_read_only_exploration(decision: Decision | None) -> bool:
    if decision is None:
        return False
    if decision.tool == "browser_scroll":
        return True
    if decision.tool != "browser_wait_for":
        return False
    args = dict(decision.args or {})
    return not str(args.get("text") or "").strip() and not str(args.get("ref") or "").strip()


def _navigation_target(
    decision: Decision | None,
    observation: Observation,
) -> Optional[dict]:
    if decision is None or decision.tool != "browser_click":
        return None
    ref = str((decision.args or {}).get("ref") or "").strip()
    if not ref:
        return None
    target = next((
        item for item in observation.elements or []
        if isinstance(item, dict) and str(item.get("ref") or "") == ref
    ), None)
    if not isinstance(target, dict):
        return None
    purpose = str(target.get("semanticPurpose") or target.get("semantic_purpose") or "")
    return target if purpose in _NAVIGATION_PURPOSES else None


__all__ = [
    "BrowserHumanAssistance",
    "EXPLORATION_STAGNATION",
    "NAVIGATION_STAGNATION",
    "NAVIGATION_TARGET_BLOCKED",
    "READ_BUDGET",
    "browser_human_assistance",
]
