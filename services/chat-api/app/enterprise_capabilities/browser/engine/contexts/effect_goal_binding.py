"""Bind verified browser effects to the mission milestone they may satisfy."""
from __future__ import annotations

from dataclasses import dataclass
from typing import AbstractSet

from app.enterprise_capabilities.browser.engine.effect_verification.contracts import EffectReceipt


_NON_BUSINESS_OPERATIONS = {
    "navigate",
    "navigation",
    "search",
    "query",
    "filter",
    "login",
    "authenticate",
    "authentication",
}


@dataclass(frozen=True)
class EffectGoalBinding:
    accepted: bool
    reason: str
    deferred: bool = False


def bind_effect_to_commit_goal(
    receipt: EffectReceipt,
    *,
    requirements: AbstractSet[str],
    completed: AbstractSet[str],
) -> EffectGoalBinding:
    """Decide whether one receipt may satisfy the mission's commit milestone.

    A successful receipt only proves that its own operation happened.  It may
    advance the task-level commit milestone after all required discovery/read
    phases have completed and only when it represents a business mutation.
    """
    if receipt.status != "confirmed_success":
        return EffectGoalBinding(False, "effect is not a confirmed success")
    if "commit" not in requirements:
        return EffectGoalBinding(False, "mission has no commit requirement")
    if receipt.side_effect == "none":
        return EffectGoalBinding(False, "effect has no business side effect")

    purpose = str((receipt.fingerprint or {}).get("interaction_purpose") or "").strip().lower()
    if purpose in _NON_BUSINESS_OPERATIONS:
        return EffectGoalBinding(False, f"receipt belongs to prerequisite interaction: {purpose}")

    pending_prerequisites = [
        name
        for name in ("navigate", "search", "open_result", "read")
        if name in requirements and name not in completed
    ]
    if pending_prerequisites:
        return EffectGoalBinding(
            False,
            "effect occurred before required mission phases: "
            + ", ".join(pending_prerequisites),
            deferred=True,
        )

    operations = {
        str(receipt.operation_family or "").strip().lower(),
        str(receipt.intended_operation or "").strip().lower(),
        str(receipt.target_operation or "").strip().lower(),
    }
    operations.discard("")
    if operations and operations.issubset(_NON_BUSINESS_OPERATIONS):
        return EffectGoalBinding(False, "receipt only represents a prerequisite operation")

    return EffectGoalBinding(True, "verified business effect matches the active commit phase")


__all__ = ["EffectGoalBinding", "bind_effect_to_commit_goal"]
