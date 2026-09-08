"""Reconcile input evidence and choose recovery before returning to planning."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from ..agent_loop.protocol import Decision, Observation
from ..form_human_assistance import build_fill_assistance_decision
from .fill_outcome import resolve_fill_outcome
from .fill_retry import FillRetryPolicy
from .observation_update import apply_confirmed_fill
from .target_preflight import is_stale_fill_target_error

if TYPE_CHECKING:
    from ..effect_verification.form_transaction import FormTransactionTracker


@dataclass(frozen=True)
class InputReconciliation:
    observation: Observation
    next_decision: Decision | None = None
    message: str = ""


def reconcile_input_step(
    *, decision: Decision, before: Observation, after: Observation,
    result: Any, ok: bool, error: str | None,
    transaction: FormTransactionTracker, retry: FillRetryPolicy, lang: str,
) -> InputReconciliation:
    if decision.tool == "browser_observe" and ok:
        next_decision = retry.after_observation(after)
        transaction.reconcile(after)
        return InputReconciliation(after, next_decision)
    if decision.tool != "browser_fill":
        return InputReconciliation(after)
    outcome = resolve_fill_outcome(result=result, ok=ok, error=error)
    confirmed = outcome.status == "confirmed"
    after = apply_confirmed_fill(after, args=decision.args, result=result, ok=confirmed, before=before)
    # A pre-input stale ref is not a business write; do not create a dirty receipt.
    if not (not ok and is_stale_fill_target_error(error) and "after input" not in str(error)):
        transaction.record_fill(
            args=decision.args, result=result, ok=ok, error=error,
            before=before, after=after,
        )
    recovery_error = error or (None if confirmed else f"value_not_applied: {outcome.reason}")
    next_decision = retry.after_result(
        decision, ok=confirmed, error=recovery_error, before=before,
    )
    if next_decision is None and not confirmed and retry.assistance_required(
        decision, error=recovery_error, before=before,
    ):
        next_decision = build_fill_assistance_decision(
            decision=decision, before=before, error=str(recovery_error or ""), lang=lang,
        )
    message = "" if confirmed else (
        "填写结果尚未确认，先核验原字段当前值，再决定恢复操作。"
        if lang.startswith("zh") else
        "Fill remains unverified; reconcile the original field before another action."
    )
    return InputReconciliation(after, next_decision, message)
