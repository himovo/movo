"""Coordinate verified browser effects with task-level completion state."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Tuple

from app.enterprise_capabilities.browser.engine.effect_verification.contracts import EffectReceipt
from app.enterprise_capabilities.browser.engine.effect_task_outcome import EffectTaskOutcome
from app.enterprise_capabilities.browser.engine.result_artifact import build_browser_result
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


@dataclass(frozen=True)
class EffectReceiptApplication:
    context_updated: bool
    outcome: EffectTaskOutcome
    error: str = ""

    @property
    def goal_completed(self) -> bool:
        return self.outcome.completed


def apply_effect_receipt(
    *,
    context: Any,
    tracks_context_state: bool,
    receipt: EffectReceipt,
    observation: Observation,
) -> EffectReceiptApplication:
    """Apply both immediate and delayed receipts through the same context hook."""
    if not tracks_context_state:
        return EffectReceiptApplication(
            context_updated=False,
            outcome=(
                EffectTaskOutcome.complete()
                if _receipt_completes_goal(receipt)
                else EffectTaskOutcome.continue_()
            ),
        )

    try:
        context.after_effect(receipt, observation)
        outcome = context.effect_task_outcome(receipt)
    except Exception as exc:
        return EffectReceiptApplication(
            context_updated=False,
            outcome=EffectTaskOutcome.continue_(),
            error=str(exc),
        )

    return EffectReceiptApplication(
        context_updated=True,
        outcome=outcome,
    )


def applied_effect_task_outcome(
    *,
    context: Any,
    tracks_context_state: bool,
    receipt: EffectReceipt | None,
) -> EffectTaskOutcome:
    """Recheck the task disposition after later page milestones are recorded."""
    if receipt is None:
        return EffectTaskOutcome.continue_()
    if not tracks_context_state:
        return (
            EffectTaskOutcome.complete()
            if _receipt_completes_goal(receipt)
            else EffectTaskOutcome.continue_()
        )
    try:
        return context.effect_task_outcome(receipt)
    except Exception:
        return EffectTaskOutcome.continue_()


def applied_effect_now_completes_goal(
    *,
    context: Any,
    tracks_context_state: bool,
    receipt: EffectReceipt | None,
) -> bool:
    """Recheck termination after later page-state milestones are recorded."""
    return applied_effect_task_outcome(
        context=context,
        tracks_context_state=tracks_context_state,
        receipt=receipt,
    ).completed


def build_effect_completion(
    *,
    receipt: EffectReceipt,
    objective: str,
    steps: int,
    lang: str,
    outcome: EffectTaskOutcome | None = None,
    result_data: Dict[str, Any] | None = None,
) -> Tuple[str, Dict[str, Any]]:
    """Build the common terminal artifact for a confirmed browser operation."""
    task_outcome = outcome or EffectTaskOutcome.complete()
    if task_outcome.status == "partial_success":
        summary = (
            f"已确认完成操作：{receipt.action_name}；但任务前置证据未完整验证，整体仅部分完成"
            if str(lang).startswith("zh")
            else
            f"Confirmed completed action: {receipt.action_name}; "
            "the overall task is only partially complete because prerequisite "
            "evidence remains unverified"
        )
    else:
        summary = (
            f"已确认完成操作：{receipt.action_name}"
            if str(lang).startswith("zh")
            else f"Confirmed completed action: {receipt.action_name}"
        )
    receipt_payload = receipt.model_dump(mode="json")
    outcome_payload = task_outcome.as_dict()
    terminal_status = (
        "ok_partial" if task_outcome.status == "partial_success" else "ok"
    )
    return summary, {
        "browser_receipt": {
            "status": terminal_status,
            "summary": summary,
            "steps": steps,
            "side_effect_status": receipt.status,
            "effect_receipt": receipt_payload,
            "task_outcome": outcome_payload,
        },
        "operation_result": receipt_payload,
        "browser_result": build_browser_result(
            objective=objective,
            summary=summary,
            data=result_data,
            operation_result=receipt_payload,
            status=(
                "partial_success"
                if task_outcome.status == "partial_success"
                else ""
            ),
            task_outcome=outcome_payload,
        ),
    }


def build_effect_failure(
    *,
    error: str,
    receipts: Iterable[Dict[str, Any]],
    status: str = "failed",
) -> Dict[str, Any]:
    """Build a terminal failure without discarding earlier side effects."""
    items = [dict(item) for item in receipts if isinstance(item, dict)]
    payload: Dict[str, Any] = {"status": status, "error": error}
    if not items:
        return payload
    active_items = [item for item in items if not _verification_superseded(item)]
    confirmed = [item for item in items if str(item.get("status") or "") == "confirmed_success"]
    payload.update({
        "effect_receipts": items,
        "confirmed_effect_count": len(confirmed),
    })
    if active_items:
        latest = active_items[-1]
        payload.update({
            "effect_receipt": latest,
            "side_effect_status": str(latest.get("status") or "unknown"),
        })
    return payload


def _verification_superseded(receipt: Dict[str, Any]) -> bool:
    fingerprint = receipt.get("fingerprint")
    return bool(
        isinstance(fingerprint, dict)
        and fingerprint.get("verification_superseded")
    )


def _receipt_completes_goal(receipt: EffectReceipt) -> bool:
    return receipt.status == "confirmed_success" and bool(receipt.completes_goal)


__all__ = [
    "EffectReceiptApplication",
    "applied_effect_task_outcome",
    "applied_effect_now_completes_goal",
    "apply_effect_receipt",
    "build_effect_completion",
    "build_effect_failure",
]
