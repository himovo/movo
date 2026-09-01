from __future__ import annotations

from typing import Any, Dict, List

from app.historical.legacy_execution_logs.recorder import BaseStreamRecorder
from app.historical.legacy_execution_logs.store import ExecutionEventStore


COLLECTION_NAME = "execution_runs_v3"


def compact_v3_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compact only final-answer deltas; semantic interaction items remain."""
    out: List[Dict[str, Any]] = []
    final_text: List[str] = []
    final_anchor: Dict[str, Any] | None = None
    final_seq_end = 0
    for event in events:
        if event.get("type") == "item.delta" and event.get("item_kind") == "final_answer":
            final_anchor = final_anchor or event
            final_text.append(str((event.get("payload") or {}).get("text") or ""))
            final_seq_end = max(final_seq_end, int(event.get("stream_seq_end") or event.get("stream_seq") or 0))
            continue
        out.append(event)
    if final_anchor and not any(e.get("type") == "item.completed" and e.get("item_kind") == "final_answer" for e in out):
        out.append({**final_anchor, "type": "item.completed", "payload": {"text": "".join(final_text)}, "stream_seq_end": final_seq_end})
    return sorted(out, key=lambda event: int(event.get("stream_seq") or 0))


def build_v3_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    tools = {
        str((event.get("payload") or {}).get("name") or "")
        for event in events
        if event.get("item_kind") == "tool"
    }
    started_at = next((int(event.get("ts") or 0) for event in events if event.get("type") == "run.started"), 0)
    terminal_types = {"run.completed", "run.failed", "run.cancelled", "run.blocked"}
    ended_at = max((int(event.get("ts") or 0) for event in events if event.get("type") in terminal_types), default=0)
    return {
        "schema_version": 3,
        "tools": sorted(name for name in tools if name),
        "artifact_count": sum(1 for e in events if e.get("item_kind") == "artifact" and e.get("type") == "item.completed"),
        "event_count": len(events),
        "failed": any(e.get("type") in {"run.failed", "item.failed"} for e in events),
        "last_stream_seq": max((int(e.get("stream_seq_end") or e.get("stream_seq") or 0) for e in events), default=0),
        "started_at": started_at or None,
        "ended_at": ended_at or None,
        "duration_ms": max(0, ended_at - started_at) if started_at and ended_at else None,
    }


class ExecutionV3Store(ExecutionEventStore):
    def __init__(self, db: Any) -> None:
        super().__init__(db, collection_name=COLLECTION_NAME, schema_version=3)


class V3StreamRecorder(BaseStreamRecorder):
    def __init__(self, store: ExecutionV3Store, session_id: str, message_id: str, **kwargs: Any) -> None:
        super().__init__(store, session_id, message_id, compact_fn=compact_v3_events, summary_fn=build_v3_summary, **kwargs)
