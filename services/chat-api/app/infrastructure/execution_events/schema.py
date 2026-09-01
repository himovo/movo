from __future__ import annotations

import json
import time
import uuid
from enum import Enum
from typing import Any, Dict, Optional


SCHEMA_VERSION = 3


class EventTypeV3(str, Enum):
    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"
    RUN_BLOCKED = "run.blocked"
    ITEM_STARTED = "item.started"
    ITEM_UPDATED = "item.updated"
    ITEM_DELTA = "item.delta"
    ITEM_COMPLETED = "item.completed"
    ITEM_FAILED = "item.failed"


class ItemKind(str, Enum):
    COMMENTARY = "commentary"
    ACTIVITY = "activity"
    FINAL_ANSWER = "final_answer"
    TOOL = "tool"
    SUBAGENT = "subagent"
    APPROVAL = "approval"
    BROWSER_HANDOFF = "browser_handoff"
    BROWSER_PREVIEW = "browser_preview"
    ARTIFACT = "artifact"
    EVIDENCE = "evidence"
    ERROR = "error"


def make_event_v3(
    type_: EventTypeV3 | str,
    *,
    item_kind: ItemKind | str | None = None,
    item_id: Optional[str] = None,
    parent_item_id: Optional[str] = None,
    revision: int = 1,
    payload: Optional[Dict[str, Any]] = None,
    event_id: Optional[str] = None,
    ts: Optional[int] = None,
) -> Dict[str, Any]:
    event: Dict[str, Any] = {
        "v": SCHEMA_VERSION,
        "event_id": event_id or uuid.uuid4().hex,
        # Keep id during the migration window because transport dedupe in the
        # existing shell is intentionally protocol-neutral.
        "id": event_id or "",
        "ts": ts or int(time.time() * 1000),
        "type": type_.value if isinstance(type_, EventTypeV3) else str(type_),
        "revision": max(1, int(revision)),
        "payload": dict(payload or {}),
    }
    if not event["id"]:
        event["id"] = event["event_id"]
    if item_kind is not None:
        event["item_kind"] = item_kind.value if isinstance(item_kind, ItemKind) else str(item_kind)
    if item_id:
        event["item_id"] = item_id
    if parent_item_id:
        event["parent_item_id"] = parent_item_id
    return event


def dumps_v3(event: Dict[str, Any]) -> str:
    return json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
