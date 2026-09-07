from __future__ import annotations

from typing import Any, Dict, List

from app.enterprise_capabilities.browser.engine.agent_loop.observation_compactor import compact_observation
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation, StepRecord


def build_turn_payload(
    goal: str,
    history: List[StepRecord],
    observation: Observation,
    state_ledger: Dict[str, Any] | None,
) -> Dict[str, Any]:
    ledger = state_ledger or {}
    pinned_refs = ledger.get("pinned_refs")
    compact = compact_observation(
        observation,
        goal=goal,
        target=str(ledger.get("target") or ""),
        pinned_refs=(pinned_refs if isinstance(pinned_refs, list) else None),
        element_budget_chars=8_000,
    )
    page_text = str(compact.get("page_text") or "")
    if page_text:
        compact["page_text"] = page_text[:2_500]
    return {
        "goal": goal[:4_000],
        "state": _compact_ledger(ledger),
        "recent_steps": [
            {
                "tool": item.decision.tool,
                "args": _bounded(item.decision.args, depth=0),
                "ok": item.ok,
                **({"error": str(item.error)[:300]} if item.error else {}),
            }
            for item in history[-4:]
        ],
        "observation": compact,
    }


def _compact_ledger(ledger: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {
        "phase", "phase_goal", "target", "completed_signals", "remaining_signals",
        "forbidden_actions", "action_constraints", "mission", "budget", "pinned_refs",
    }
    return {key: _bounded(value, depth=0) for key, value in ledger.items() if key in allowed}


def _bounded(value: Any, *, depth: int) -> Any:
    if depth >= 3:
        return str(value)[:300]
    if isinstance(value, str):
        return value[:1_000]
    if isinstance(value, dict):
        return {
            str(key)[:120]: _bounded(item, depth=depth + 1)
            for key, item in list(value.items())[:20]
        }
    if isinstance(value, list):
        return [_bounded(item, depth=depth + 1) for item in value[:20]]
    return value
