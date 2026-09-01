"""Bridge browser human-intervention pauses to the runtime suspension service."""

from __future__ import annotations

from typing import Any, Dict

from app.governance.suspensions import SuspensionType, suspension_service
from app.governance.suspensions.contracts import SuspensionRecord


async def suspend_browser_intervention(
    *,
    run_id: str,
    task_id: str,
    node_id: str,
    user_id: str,
    subagent_id: str,
    browser_session_id: str,
    tab_id: str,
    category: str,
    reason: str,
    url: str,
    handoff: Dict[str, Any] | None = None,
    mission: Dict[str, Any] | None = None,
) -> SuspensionRecord:
    """Create the standard resumable record for a browser human handoff."""

    return await suspension_service.suspend(
        run_id=run_id,
        task_id=task_id,
        node_id=node_id,
        user_id=user_id,
        subagent_id=subagent_id,
        suspension_type=SuspensionType.USER_INPUT.value,
        reason=reason,
        resume_policy="manual",
        context={
            "browser_session_id": browser_session_id,
            "tab_id": tab_id,
            "category": category,
            "url": url,
            **({"handoff": dict(handoff)} if handoff else {}),
            **({"mission": dict(mission)} if mission else {}),
        },
    )


def browser_resume_context(record: SuspensionRecord) -> Dict[str, Any]:
    context = dict(record.context or {})
    return {
        "suspension_id": record.suspension_id,
        "run_id": record.run_id,
        "node_id": record.node_id,
        "browser_session_id": str(context.get("browser_session_id") or record.task_id),
        "tab_id": str(context.get("tab_id") or ""),
        "resumable": True,
    }


def bind_browser_resume_signal(
    record: SuspensionRecord,
    signal: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """Bind a client outcome to the server-stored assistance contract."""
    resolved = dict(signal or {})
    context = dict(record.context or {})
    handoff = context.get("handoff")
    contract = handoff.get("contract") if isinstance(handoff, dict) else None
    if isinstance(contract, dict):
        resolved["assistance_contract"] = dict(contract)
    else:
        resolved.pop("assistance_contract", None)
    return resolved
