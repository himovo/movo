"""Close a persisted assistant run when the native runner no longer owns it."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def terminal_event(message_id: str, status: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    sequence = max((int(event.get("stream_seq") or 0) for event in events), default=0) + 1
    event_id = f"dsh-v3:{message_id}:terminal:{status}"
    return {
        "v": 3, "event_id": event_id, "id": event_id,
        "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
        "type": f"run.{status}", "revision": sequence,
        "stream_seq": sequence, "stream_seq_end": sequence,
        "payload": {"reason": "finalized"},
    }


def with_terminal(message_id: str, status: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if any(event.get("type") in {"run.completed", "run.failed", "run.cancelled"} for event in events):
        return events
    return [*events, terminal_event(message_id, status, events)]
