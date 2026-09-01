from __future__ import annotations

from typing import Any, Dict, Mapping


def build_browser_result(
    *,
    objective: str,
    summary: str,
    data: Mapping[str, Any] | None = None,
    operation_result: Mapping[str, Any] | None = None,
    status: str = "",
    task_outcome: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build the browser node's stable, downstream-facing result contract."""
    operation = dict(operation_result or {})
    result_data = dict(data or {})
    is_operation = bool(operation)
    resolved_status = str(
        status
        or operation.get("status")
        or ("completed" if result_data or summary else "unknown")
    )
    result: Dict[str, Any] = {
        "schema_version": 1,
        "kind": "operation" if is_operation else "observation",
        "status": resolved_status,
        "objective": str(objective or "").strip(),
        "summary": str(summary or "").strip(),
        "data": result_data,
    }
    if task_outcome:
        result["task_outcome"] = dict(task_outcome)
    if is_operation:
        result["operation"] = operation
        result["verification_boundary"] = (
            "The observed application state transition is confirmed. "
            "Do not claim downstream business outcomes unless the evidence explicitly confirms them."
        )
    return result


def build_recovered_browser_result(
    *,
    objective: str,
    summary: str,
    browser_receipt: Mapping[str, Any] | None,
    status: str = "partial_success",
) -> Dict[str, Any]:
    """Normalize a recovered browser node into the canonical result contract."""
    receipt = dict(browser_receipt or {})
    operation = receipt.get("effect_receipt")
    if not isinstance(operation, dict):
        effects = [
            dict(item)
            for item in list(receipt.get("effect_receipts") or [])
            if isinstance(item, dict)
        ]
        confirmed = [
            item for item in effects
            if str(item.get("status") or "") == "confirmed_success"
        ]
        operation = (confirmed or effects or [{}])[-1]
    task_outcome = {
        "status": status,
        "reason": str(
            receipt.get("reason")
            or receipt.get("error")
            or "browser node recovered with partial evidence"
        ),
    }
    return build_browser_result(
        objective=objective,
        summary=summary,
        data={"recovery": task_outcome},
        operation_result=operation if operation else None,
        status=status,
        task_outcome=task_outcome,
    )


__all__ = ["build_browser_result", "build_recovered_browser_result"]
