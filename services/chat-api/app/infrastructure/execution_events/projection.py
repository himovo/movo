from __future__ import annotations

from typing import Any, Dict, List


class V3RunProjection:
    """Projects the V3 event log into the persisted assistant message."""

    def __init__(self) -> None:
        self.text_parts: List[str] = []
        self.documents: List[Dict[str, Any]] = []
        self.evidence: List[Dict[str, Any]] = []
        self.events: List[Dict[str, Any]] = []
        self.suspended = False
        self.failed = False

    def observe(self, event: Dict[str, Any]) -> None:
        self.events.append(event)
        kind = str(event.get("item_kind") or "")
        event_type = str(event.get("type") or "")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if event_type == "run.failed":
            self.failed = True
        if kind == "final_answer":
            if event_type == "item.delta":
                self.text_parts.append(str(payload.get("text") or ""))
            elif event_type == "item.completed" and isinstance(payload.get("text"), str):
                self.text_parts = [str(payload.get("text") or "")]
        elif kind == "artifact" and event_type == "item.completed":
            self.documents.append(dict(payload))
        elif kind == "evidence" and event_type == "item.completed":
            self.evidence.append(dict(payload))
        elif kind == "browser_handoff" and event_type in {"item.started", "item.updated"}:
            self.suspended = bool(payload.get("resumable"))

    def result(self) -> tuple[List[str], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], bool]:
        return self.text_parts, self.documents, self.evidence, self.events, self.suspended
