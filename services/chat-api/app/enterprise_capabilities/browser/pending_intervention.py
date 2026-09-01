"""Prevent duplicate browser missions while a human handoff is active."""

from __future__ import annotations

from typing import Any

from app.enterprise_capabilities.browser.engine.intervention_suspension import browser_resume_context
from app.governance.suspensions import SuspensionType, suspension_service


async def pending_browser_result(*, user_id: str, conversation_id: str) -> dict[str, Any] | None:
    try:
        record = await suspension_service.store.latest_active(
            user_id=user_id,
            task_id=conversation_id,
            suspension_type=SuspensionType.USER_INPUT.value,
        )
    except Exception:
        return None
    if record is None:
        return None
    context = dict(record.context or {})
    if not str(context.get("browser_session_id") or ""):
        return None
    suspension = browser_resume_context(record)
    event = {
        "type": "intervention_required",
        "content": {
            "reason": record.reason,
            "category": str(context.get("category") or "browser"),
            "url": str(context.get("url") or ""),
            **suspension,
        },
    }
    return {
        "success": True,
        "status": "suspended_waiting_approval",
        "responseSummary": "Browser assistance is already pending. Stop this turn and wait for the user to resume it.",
        "intervention_suspension": suspension,
        "artifacts": {"intervention_suspension": suspension},
        "domain_events": [event],
        "event_counts": {"intervention_required": 1},
    }


__all__ = ["pending_browser_result"]
