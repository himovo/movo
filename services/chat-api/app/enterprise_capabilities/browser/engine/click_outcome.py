"""Interpret native browser click receipts without changing graph semantics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


@dataclass(frozen=True)
class ClickOutcome:
    ok: bool
    error: str | None = None
    delivered: bool = False
    progressed: bool = False


class ClickOutcomePolicy:
    """Stops replay of a click that was delivered but did not advance state."""

    def __init__(self) -> None:
        self._unproductive: set[tuple[tuple[Any, ...], str]] = set()

    def blocker(self, decision: Decision, observation: Observation) -> str | None:
        identity = _click_identity(decision)
        if not identity:
            return None
        if (_state_key(observation), identity) not in self._unproductive:
            return None
        return (
            "同一页面上的这个点击已成功投递，但页面没有推进。"
            "不要重复点击同一元素；请重新观察遮挡层、新标签页、禁用状态或选择其他目标。"
        )

    def evaluate(
        self,
        decision: Decision,
        result: Any,
        before: Observation,
    ) -> ClickOutcome:
        identity = _click_identity(decision)
        receipt = _receipt(result)
        if not identity or not receipt:
            return ClickOutcome(ok=True)
        status = str(receipt.get("status") or "")
        key = (_state_key(before), identity)
        if status == "delivered":
            self._unproductive.add(key)
            return ClickOutcome(
                ok=False,
                error=(
                    "点击事件已投递到目标，但 URL、标签页、焦点、交互元素和页面文本均未变化。"
                    "请重新观察页面并换策略，不要重复点击同一 ref。"
                ),
                delivered=True,
            )
        if status == "progressed":
            self._unproductive.clear()
            return ClickOutcome(ok=True, delivered=True, progressed=True)
        return ClickOutcome(ok=True)


def effect_verification_eligible(
    *,
    prepared_effect: Any,
    action_ok: bool,
    click_outcome: ClickOutcome,
) -> bool:
    """Allow business verification after a delivered commit click.

    A click can be delivered without changing URL, focus, or the stable DOM.
    Its latest observation may still contain a transient success/failure state,
    which belongs to the effect verifier rather than click progress detection.
    """
    return prepared_effect is not None and (action_ok or click_outcome.delivered)


def _receipt(result: Any) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    receipt = result.get("action_receipt")
    return receipt if isinstance(receipt, dict) else None


def _click_identity(decision: Decision) -> str:
    if decision.tool == "browser_click":
        ref = str((decision.args or {}).get("ref") or "").strip()
        return f"ref:{ref}" if ref else ""
    if decision.tool == "browser_click_at":
        args = decision.args or {}
        return f"point:{args.get('x')}:{args.get('y')}"
    return ""


def _state_key(observation: Observation) -> tuple[Any, ...]:
    interaction = observation.interaction or {}
    elements = observation.elements or []
    interactive_state = tuple(
        (
            str(item.get("ref") or ""),
            str(item.get("role") or ""),
            str(item.get("value") or ""),
            bool(item.get("focused")),
            bool(item.get("disabled")),
            bool(item.get("visible", True)),
            str(item.get("scopeId") or item.get("scope_id") or ""),
        )
        for item in elements
        if isinstance(item, dict)
    )
    return (
        observation.url,
        interaction.get("tabId") or interaction.get("tab_id") or "",
        hash(interactive_state),
        hash(observation.page_text or ""),
    )


__all__ = [
    "ClickOutcome",
    "ClickOutcomePolicy",
    "effect_verification_eligible",
]
