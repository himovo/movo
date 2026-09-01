"""Project real presentation pipeline stages under the DSH Tool action."""

from __future__ import annotations

import re
from time import time
from typing import Any


class PresentationTimelineProjector:
    def __init__(self, *, action_id: str, message_id: str) -> None:
        self._action_id = action_id
        self._namespace = f"{message_id or 'no-message'}:{action_id}"
        self._counter = 0

    def project(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        text = re.sub(r"\s+", " ", str(payload.get("message") or "")).strip()[:1000]
        if not text:
            return None
        self._counter += 1
        event_id = f"askai-v3:presentation:{self._namespace}:{self._counter}"
        return {
            "v": 3,
            "event_id": event_id,
            "id": event_id,
            "ts": int(time() * 1000),
            "type": "item.completed",
            "item_kind": "commentary",
            "item_id": f"{self._action_id}:presentation-progress:{self._counter}",
            "parent_item_id": self._action_id,
            "revision": 1,
            "payload": {
                "text": text,
                "source": "presentation_pipeline",
                "reason": str(payload.get("stage") or payload.get("kind") or "presentation"),
            },
        }


__all__ = ["PresentationTimelineProjector"]
