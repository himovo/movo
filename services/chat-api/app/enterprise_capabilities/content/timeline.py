from __future__ import annotations

import re
from time import time
from typing import Any


class ContentTimelineProjector:
    """Project producer-owned writer progress under the DSH tool action."""

    def __init__(self, *, outer_action_id: str, message_id: str = "") -> None:
        self._outer_action_id = outer_action_id
        self._namespace = f"{message_id or 'no-message'}:{outer_action_id}"
        self._counter = 0

    def project(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        if str(event.get("type") or "").strip().lower() not in {"activity", "commentary"}:
            return []
        content = event.get("content")
        if isinstance(content, dict):
            text = content.get("message") or content.get("text")
            kind = str(content.get("kind") or "writing")
        else:
            text, kind = content, "writing"
        text = re.sub(r"\s+", " ", str(text or "")).strip()[:1000]
        if not text:
            return []
        self._counter += 1
        event_id = f"askai-v3:content:{self._namespace}:{self._counter}"
        return [{
            "v": 3,
            "event_id": event_id,
            "id": event_id,
            "ts": int(time() * 1000),
            "type": "item.completed",
            "item_kind": "commentary",
            "item_id": f"{self._outer_action_id}:content-progress:{self._counter}",
            "parent_item_id": self._outer_action_id,
            "revision": 1,
            "payload": {"text": text, "source": "writer_pipeline", "reason": kind},
        }]


__all__ = ["ContentTimelineProjector"]
