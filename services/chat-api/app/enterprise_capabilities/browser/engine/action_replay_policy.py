"""Deterministic cross-run policy for confirmed browser mutations.

The cross-run guard is a safety net, not a semantic planner.  It only blocks
cases whose identity is locally provable; broader business questions such as
whether an actor has already commented belong to DSH and current-page
evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.enterprise_capabilities.browser.engine.effect_verification.contracts import (
    EffectContract,
)


ScopeDimension = Literal["actor", "system", "target", "operation", "purpose", "payload"]


@dataclass(frozen=True)
class DeterministicReplayPolicy:
    guard_across_runs: bool = False
    scope_dimensions: tuple[ScopeDimension, ...] = ()
    purpose: str = ""
    reason: str = ""


def resolve_deterministic_replay_policy(
    contract: EffectContract,
    *,
    target_id: str,
    operation_id: str,
    payload_id: str,
) -> DeterministicReplayPolicy:
    """Return a fail-open policy without consulting a model.

    Exact payload replay is safe to block across runs.  Destructive actions
    are also target-scoped because repeating them cannot create a useful
    second business result.  Other writes remain repeatable unless DSH has
    established their business semantics from the live page.
    """
    target = str(target_id or "").strip()
    operation = str(operation_id or "").strip()
    if not contract.is_commit or not target or not operation:
        return DeterministicReplayPolicy(reason="durable action identity unavailable")

    purpose = operation[:240]
    if str(payload_id or "").strip():
        return DeterministicReplayPolicy(
            guard_across_runs=True,
            scope_dimensions=("actor", "system", "target", "operation", "payload"),
            purpose=purpose,
            reason="same durable target, operation, and business payload",
        )
    if contract.side_effect == "destructive":
        return DeterministicReplayPolicy(
            guard_across_runs=True,
            scope_dimensions=("actor", "system", "target", "operation"),
            purpose=purpose,
            reason="same destructive operation on the same durable target",
        )
    return DeterministicReplayPolicy(
        purpose=purpose,
        reason="repeatability cannot be proven from deterministic evidence",
    )


__all__ = [
    "DeterministicReplayPolicy",
    "ScopeDimension",
    "resolve_deterministic_replay_policy",
]
