"""Planner feedback after a form commit control is rejected."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Protocol

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import (
    Decision,
    Observation,
    StepRecord,
)

from .commit_binding import CommitBindingLedger
from .contracts import FieldDescriptor


logger = logging.getLogger(__name__)


class _PlannerDriver(Protocol):
    async def next_step(
        self,
        goal: str,
        history: List[StepRecord],
        observation: Observation,
        state_ledger: Optional[Dict[str, Any]] = None,
    ) -> Decision: ...


async def replan_rejected_commit(
    *,
    ledger: CommitBindingLedger,
    planner: _PlannerDriver,
    decision: Decision,
    goal: str,
    history: List[StepRecord],
    observation: Observation,
    fields: List[FieldDescriptor],
    state_ledger: Optional[Dict[str, Any]],
) -> Decision:
    """Give one rejected selection back to the existing planner.

    Dispatch validation remains the final authority. This helper only makes
    that validation result visible to the next model decision and allows one
    bounded correction without adding another browser state machine.
    """
    if not ledger.is_rejected_decision(
        decision,
        observation,
        fields=fields,
    ):
        return decision

    retry_ledger = ledger.augment_planner_state(
        observation=observation,
        fields=fields,
        state_ledger=state_ledger,
        repeated_selection=True,
    )
    rejected = StepRecord(
        observation=observation,
        decision=decision,
        ok=False,
        error=(
            "This control was already rejected because it is not bound "
            "to the active edited form. Select another current candidate."
        ),
    )
    logger.info(
        "browser rejected form action sent back to planner",
        extra={
            "event": "browser.form_commit_replanned",
            "ref": str((decision.args or {}).get("ref") or ""),
        },
    )
    corrected = await planner.next_step(
        goal,
        [*history, rejected],
        observation,
        state_ledger=retry_ledger,
    )
    if not ledger.is_rejected_decision(
        corrected,
        observation,
        fields=fields,
    ):
        return corrected
    return Decision(
        tool="browser_observe",
        args={},
        rationale=(
            "[form_commit_replan] the planner repeated a control already "
            "rejected for this form stage; refresh before selecting a "
            "different form-local action"
        ),
    )


__all__ = ["replan_rejected_commit"]
