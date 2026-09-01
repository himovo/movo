from __future__ import annotations

from time import time
from typing import Any

from app.enterprise_capabilities.evidence.foundation import build_user_evidence_payload


def project_execution_evidence(
    bundle: dict[str, Any] | None,
    *,
    evidence_id: str = "",
) -> dict[str, Any]:
    """Convert execution-scoped evidence into the user-facing source contract."""
    if not isinstance(bundle, dict) or not bundle:
        return {}
    payload = build_user_evidence_payload(bundle)
    if not payload:
        return {}
    return {"id": evidence_id, **payload} if evidence_id else payload


def build_execution_evidence_event(
    *,
    message_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    evidence_id = str(payload.get("id") or f"evidence-{message_id}")
    return {
        "v": 3,
        "event_id": f"execution-evidence:{message_id}",
        "id": f"execution-evidence:{message_id}",
        "ts": int(time() * 1000),
        "type": "item.completed",
        "item_kind": "evidence",
        "item_id": evidence_id,
        "revision": 1,
        "payload": payload,
    }


__all__ = ["build_execution_evidence_event", "project_execution_evidence"]
