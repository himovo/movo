"""Build a terminal browser result for an explicitly rejected business action."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.enterprise_capabilities.browser.engine.effect_verification.contracts import EffectReceipt
from app.enterprise_capabilities.browser.engine.result_artifact import build_browser_result


def build_effect_business_failure(
    *,
    receipt: EffectReceipt,
    objective: str,
    steps: int,
    lang: str,
    result_data: Dict[str, Any] | None = None,
) -> Tuple[str, Dict[str, Any]]:
    """Return a known negative business result without reporting a runtime crash."""
    reason = str(receipt.reason or "").strip()
    action = str(receipt.action_name or "").strip()
    if str(lang or "").startswith("zh"):
        summary = f"“{action}”未完成：页面明确拒绝了本次操作"
        if reason:
            summary += f"（{reason}）"
        summary += "。任务已停止，未重复提交。"
    else:
        summary = f'"{action}" was not completed because the page rejected the operation'
        if reason:
            summary += f" ({reason})"
        summary += ". The task stopped without replaying the submission."

    receipt_payload = receipt.model_dump(mode="json")
    task_outcome = {
        "status": "business_failure",
        "reason": reason,
        "verified_requirements": [],
        "missing_requirements": [],
    }
    return summary, {
        "browser_receipt": {
            "status": "business_rejected",
            "summary": summary,
            "reason": reason,
            "steps": steps,
            "side_effect_status": receipt.status,
            "effect_receipt": receipt_payload,
            "task_outcome": task_outcome,
        },
        "operation_result": receipt_payload,
        "browser_result": build_browser_result(
            objective=objective,
            summary=summary,
            data=result_data,
            operation_result=receipt_payload,
            status="confirmed_failure",
            task_outcome=task_outcome,
        ),
    }


def build_effect_business_failure_events(
    *,
    receipt: EffectReceipt,
    objective: str,
    steps: int,
    lang: str,
    result_data: Dict[str, Any] | None,
    subagent_id: str,
    node_id: str,
    emit_answer: bool,
) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """Build the terminal event sequence for a known business rejection."""
    summary, metadata = build_effect_business_failure(
        receipt=receipt,
        objective=objective,
        steps=steps,
        lang=lang,
        result_data=result_data,
    )
    events: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    events.append(({
        "type": "activity",
        "content": {"kind": "warning", "message": summary},
    }, {}))
    if emit_answer:
        events.append(({"type": "answer", "content": summary}, {}))
    events.append(({
        "type": "subagent_done",
        "content": {
            "subagent_id": subagent_id,
            "node_id": node_id,
            # The browser executor completed normally and returned a verified
            # negative business outcome. It did not crash.
            "status": "succeeded",
        },
    }, metadata))
    return events


__all__ = [
    "build_effect_business_failure",
    "build_effect_business_failure_events",
]
