"""ASKAI-owned V3 events for the enterprise approval state machine."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .contracts import EnterpriseApproval


def approval_requested_event(
    approval: EnterpriseApproval,
    *,
    display_name: str,
    description: str,
    risk_level: str,
) -> dict[str, Any]:
    return _event(
        approval,
        event_type="item.started",
        revision=1,
        payload={
            "source": "askai-approval",
            "action_id": approval.action_id,
            "request_id": approval.action_id,
            "tool_name": approval.tool_name,
            "display_name": display_name,
            "description": description,
            "risk_level": risk_level,
            "args": dict(approval.arguments),
            "policy_reason": approval.reason,
            "scope_label": approval.scope_label,
            "status": "pending",
        },
    )


def approval_resolved_event(approval: EnterpriseApproval) -> dict[str, Any]:
    terminal_type = "item.completed" if approval.status == "approved" else "item.failed"
    return _event(
        approval,
        event_type=terminal_type,
        revision=2,
        payload={
            "source": "askai-approval",
            "action_id": approval.action_id,
            "tool_name": approval.tool_name,
            "outcome": approval.status,
            "grant_scope": approval.grant_scope,
            "status": approval.status,
        },
    )


def _event(
    approval: EnterpriseApproval,
    *,
    event_type: str,
    revision: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    return {
        "v": 3,
        "event_id": f"askai-approval:{approval.action_id}:{revision}",
        "id": f"askai-approval:{approval.action_id}:{revision}",
        "ts": now_ms,
        "type": event_type,
        "item_kind": "approval",
        "item_id": approval.action_id,
        "revision": revision,
        "payload": payload,
    }
