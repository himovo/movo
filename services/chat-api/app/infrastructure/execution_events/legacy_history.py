from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

from .schema import EventTypeV3, ItemKind, make_event_v3


class LegacyHistoryImporter:
    """Read retired execution logs into V3 without reactivating old runtime paths."""

    def __init__(self) -> None:
        self._started = False
        self._final_id = "final_answer"
        self._final_started = False
        self._final_completed = False
        self._final_text: List[str] = []
        self._final_revision = 0
        self._blocked = False
        self._terminal = False
        self._tool_ids: Dict[str, List[str]] = defaultdict(list)
        self._item_revisions: Dict[str, int] = {}
        self._counter = 0
        self._planning_item_id = "commentary_planning"
        self._planning_started = False
        self._planning_completed = False

    def _id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}_{self._counter}"

    def _revision(self, item_id: str) -> int:
        revision = self._item_revisions.get(item_id, 0) + 1
        self._item_revisions[item_id] = revision
        return revision

    def _start_run(self, ts: int) -> List[Dict[str, Any]]:
        if self._started:
            return []
        self._started = True
        return [make_event_v3(EventTypeV3.RUN_STARTED, payload={}, ts=ts)]

    def start(self, *, include_planning: bool = False) -> List[Dict[str, Any]]:
        """Start V3 immediately, before the legacy pipeline yields its first event."""
        out = self._start_run(0)
        if include_planning and not self._planning_started:
            self._planning_started = True
            out.append(make_event_v3(
                EventTypeV3.ITEM_STARTED,
                item_kind=ItemKind.COMMENTARY,
                item_id=self._planning_item_id,
                revision=self._revision(self._planning_item_id),
                payload={"kind": "planning"},
            ))
        return out

    def _complete_planning(self, ts: int | None) -> List[Dict[str, Any]]:
        if not self._planning_started or self._planning_completed:
            return []
        self._planning_completed = True
        return [make_event_v3(
            EventTypeV3.ITEM_COMPLETED,
            item_kind=ItemKind.COMMENTARY,
            item_id=self._planning_item_id,
            revision=self._revision(self._planning_item_id),
            payload={"kind": "planning_completed"},
            ts=ts,
        )]

    def translate(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        ts = int(event.get("ts") or 0) or None
        event_type = str(event.get("type") or "")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        node_id = str(event.get("node_id") or "root")
        out = self._start_run(ts or 0)

        if event_type == "session.start":
            return out
        out.extend(self._complete_planning(ts))
        if event_type == "task.created":
            return out
        if event_type == "task.progress":
            item_id = self._id("commentary")
            out.append(make_event_v3(
                EventTypeV3.ITEM_COMPLETED,
                item_kind=ItemKind.COMMENTARY,
                item_id=item_id,
                parent_item_id=node_id,
                payload=dict(payload),
                ts=ts,
            ))
        elif event_type == "tool.call":
            name = str(payload.get("tool") or "tool")
            item_id = self._id("tool")
            self._tool_ids[name].append(item_id)
            revision = self._revision(item_id)
            out.append(make_event_v3(
                EventTypeV3.ITEM_STARTED,
                item_kind=ItemKind.TOOL,
                item_id=item_id,
                parent_item_id=node_id,
                revision=revision,
                payload={"name": name, "args": payload.get("args") or {}},
                ts=ts,
            ))
        elif event_type in {"tool.progress", "tool.result"}:
            name = str(payload.get("tool") or "tool")
            item_id = self._tool_ids[name][-1] if self._tool_ids[name] else self._id("tool")
            revision = self._revision(item_id)
            target_type = EventTypeV3.ITEM_UPDATED if event_type == "tool.progress" else (
                EventTypeV3.ITEM_COMPLETED if payload.get("ok", True) else EventTypeV3.ITEM_FAILED
            )
            out.append(make_event_v3(
                target_type,
                item_kind=ItemKind.TOOL,
                item_id=item_id,
                parent_item_id=node_id,
                revision=revision,
                payload={"name": name, **dict(payload)},
                ts=ts,
            ))
            if event_type == "tool.result" and self._tool_ids[name]:
                self._tool_ids[name].pop()
        elif event_type == "text.delta":
            if not self._final_started:
                self._final_started = True
                self._final_revision = 1
                out.append(make_event_v3(
                    EventTypeV3.ITEM_STARTED,
                    item_kind=ItemKind.FINAL_ANSWER,
                    item_id=self._final_id,
                    payload={},
                    ts=ts,
                ))
            text = str(payload.get("text") or "")
            self._final_text.append(text)
            self._final_revision += 1
            out.append(make_event_v3(
                EventTypeV3.ITEM_DELTA,
                item_kind=ItemKind.FINAL_ANSWER,
                item_id=self._final_id,
                revision=self._final_revision,
                payload={"text": text},
                ts=ts,
            ))
        elif event_type == "text.done":
            text = str(payload.get("text") or "") or "".join(self._final_text)
            self._final_started = True
            self._final_completed = True
            self._final_text = [text]
            self._final_revision += 1
            out.append(make_event_v3(
                EventTypeV3.ITEM_COMPLETED,
                item_kind=ItemKind.FINAL_ANSWER,
                item_id=self._final_id,
                revision=max(2, self._final_revision),
                payload={"text": text},
                ts=ts,
            ))
        elif event_type == "artifact":
            out.append(make_event_v3(EventTypeV3.ITEM_COMPLETED, item_kind=ItemKind.ARTIFACT, item_id=self._id("artifact"), payload=dict(payload), ts=ts))
        elif event_type == "evidence.bundle":
            out.append(make_event_v3(EventTypeV3.ITEM_COMPLETED, item_kind=ItemKind.EVIDENCE, item_id=self._id("evidence"), payload=dict(payload), ts=ts))
        elif event_type == "subagent.spawned":
            item_id = str(event.get("node_id") or self._id("subagent"))
            out.append(make_event_v3(EventTypeV3.ITEM_STARTED, item_kind=ItemKind.SUBAGENT, item_id=item_id, revision=self._revision(item_id), payload=dict(payload), ts=ts))
        elif event_type == "subagent.done":
            status_type = EventTypeV3.ITEM_FAILED if payload.get("status") == "failed" else EventTypeV3.ITEM_COMPLETED
            item_id = str(event.get("node_id") or payload.get("subagent_id") or self._id("subagent"))
            out.append(make_event_v3(status_type, item_kind=ItemKind.SUBAGENT, item_id=item_id, revision=self._revision(item_id), payload=dict(payload), ts=ts))
        elif event_type == "permission.required":
            item_id = str(payload.get("request_id") or self._id("approval"))
            out.append(make_event_v3(EventTypeV3.ITEM_STARTED, item_kind=ItemKind.APPROVAL, item_id=item_id, revision=self._revision(item_id), payload=dict(payload), ts=ts))
        elif event_type == "permission.resolved":
            item_id = str(payload.get("request_id") or self._id("approval"))
            out.append(make_event_v3(EventTypeV3.ITEM_COMPLETED, item_kind=ItemKind.APPROVAL, item_id=item_id, revision=self._revision(item_id), payload=dict(payload), ts=ts))
        elif event_type == "browser.preview":
            item_id = "browser_preview"
            out.append(make_event_v3(EventTypeV3.ITEM_UPDATED, item_kind=ItemKind.BROWSER_PREVIEW, item_id=item_id, revision=self._revision(item_id), payload=dict(payload), ts=ts))
        elif event_type == "intervention":
            target = EventTypeV3.ITEM_COMPLETED if payload.get("cleared") else EventTypeV3.ITEM_STARTED
            item_id = "browser_handoff"
            out.append(make_event_v3(target, item_kind=ItemKind.BROWSER_HANDOFF, item_id=item_id, revision=self._revision(item_id), payload=dict(payload), ts=ts))
            if not payload.get("cleared"):
                self._blocked = True
                out.append(make_event_v3(EventTypeV3.RUN_BLOCKED, payload=dict(payload), ts=ts))
            else:
                self._blocked = False
        elif event_type == "error":
            out.append(make_event_v3(EventTypeV3.ITEM_FAILED, item_kind=ItemKind.ERROR, item_id=self._id("error"), payload=dict(payload), ts=ts))
            out.append(make_event_v3(EventTypeV3.RUN_FAILED, payload=dict(payload), ts=ts))
            self._terminal = True
        elif event_type == "run.cancelled":
            out.append(make_event_v3(EventTypeV3.RUN_CANCELLED, payload=dict(payload), ts=ts))
            self._terminal = True
        elif event_type == "session.end":
            if self._final_started and not self._final_completed and not self._blocked and not self._terminal:
                self._final_revision += 1
                out.append(make_event_v3(EventTypeV3.ITEM_COMPLETED, item_kind=ItemKind.FINAL_ANSWER, item_id=self._final_id, revision=self._final_revision, payload={"text": "".join(self._final_text)}, ts=ts))
                self._final_completed = True
            if not self._blocked and not self._terminal:
                out.append(make_event_v3(EventTypeV3.RUN_COMPLETED, payload={}, ts=ts))
                self._terminal = True
        return out

