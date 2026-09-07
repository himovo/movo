"""Expose atomic actions from a sidecar action plan to browser contexts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation
from app.enterprise_capabilities.browser.engine.contexts.action_transition import BrowserActionTransition


@dataclass(frozen=True)
class ContextActionTransition:
    transition: BrowserActionTransition
    result: Any
    ok: bool
    error: Optional[str]


def context_action_transitions(
    decision: Decision,
    *,
    result: Any,
    ok: bool,
    error: Optional[str],
    before: Observation,
    after: Observation,
) -> List[ContextActionTransition]:
    if decision.tool != "browser_execute_plan":
        return [_item(decision, result, ok, error, before, after)]

    actions = list((decision.args or {}).get("actions") or [])
    if not actions or not isinstance(result, dict):
        return [_item(decision, result, ok, error, before, after)]
    receipts = {
        int(receipt.get("index")): receipt
        for receipt in list(result.get("receipts") or [])
        if isinstance(receipt, dict) and str(receipt.get("index", "")).isdigit()
    }
    expanded: List[ContextActionTransition] = []
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            continue
        receipt = receipts.get(index)
        action_ok = bool(receipt and receipt.get("status") == "completed")
        if receipt is None and ok:
            action_ok = True
        if not action_ok:
            continue
        atomic = Decision(
            tool=str(action.get("tool") or ""),
            args=dict(action.get("args") or {}),
            rationale=decision.rationale,
            rationale_source=decision.rationale_source,
        )
        expanded.append(_item(
            atomic,
            receipt.get("detail") if receipt and "detail" in receipt else {},
            True,
            None,
            before,
            after,
        ))
    return expanded or [_item(decision, result, ok, error, before, after)]


def _item(
    decision: Decision,
    result: Any,
    ok: bool,
    error: Optional[str],
    before: Observation,
    after: Observation,
) -> ContextActionTransition:
    return ContextActionTransition(
        transition=BrowserActionTransition.capture(decision, before=before, after=after),
        result=result,
        ok=ok,
        error=error,
    )


__all__ = ["ContextActionTransition", "context_action_transitions"]
