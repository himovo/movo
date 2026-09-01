"""Projection of progressive research lifecycles into ASKAI V3 rows."""

from __future__ import annotations

import re
from time import time
from typing import Any


class ResearchTimelineProjector:
    """Keep research semantics producer-owned while namespacing UI lifecycle IDs."""

    def __init__(self, *, outer_action_id: str, message_id: str = "") -> None:
        self._outer_action_id = outer_action_id
        self._namespace = f"{message_id or 'no-message'}:{outer_action_id}"
        self._counter = 0
        self._operations: dict[str, dict[str, str]] = {}

    def project(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        event_type = str(event.get("type") or "").strip().lower()
        content = dict(event.get("content") or {}) if isinstance(event.get("content"), dict) else {}
        if event_type.startswith("operation."):
            return self._operation(event_type, content)
        if event_type == "commentary" and str(content.get("source") or "model") == "model":
            text = self._text(content.get("text") or content.get("message"))
            if text:
                return [self._row(
                    event_type="item.completed",
                    item_id=self._new_item_id("commentary"),
                    revision=1,
                    item_kind="commentary",
                    payload={"text": text, "source": "model", "reason": "research_decision"},
                )]
        return []

    def _operation(self, event_type: str, content: dict[str, Any]) -> list[dict[str, Any]]:
        native_id = str(content.get("operation_id") or "").strip()
        if not native_id:
            return []
        item_id = f"{self._outer_action_id}:research:{native_id}"
        state = event_type.removeprefix("operation.")
        existing = self._operations.get(native_id, {})
        label = self._text(content.get("label")) or existing.get("label", "")
        category = str(content.get("category") or existing.get("category") or "search")
        if state == "started":
            self._operations[native_id] = {"label": label, "category": category}
        payload: dict[str, Any] = {
            "label": label,
            "category": category,
            "source": "progressive_research",
        }
        if isinstance(content.get("detail"), dict):
            payload["detail"] = dict(content["detail"])
        projected = {
            "started": "item.started",
            "completed": "item.completed",
            "failed": "item.failed",
            "blocked": "item.failed",
            "updated": "item.updated",
        }.get(state)
        if projected is None:
            return []
        revision = 1 if state == "started" else 2
        return [self._row(
            event_type=projected,
            item_id=item_id,
            revision=revision,
            item_kind="activity",
            payload=payload,
        )]

    def _new_item_id(self, kind: str) -> str:
        self._counter += 1
        return f"{self._outer_action_id}:research-{kind}:{self._counter}"

    def _row(
        self,
        *,
        event_type: str,
        item_id: str,
        revision: int,
        item_kind: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self._counter += 1
        event_id = f"askai-v3:research:{self._namespace}:{self._counter}"
        return {
            "v": 3,
            "event_id": event_id,
            "id": event_id,
            "ts": int(time() * 1000),
            "type": event_type,
            "item_kind": item_kind,
            "item_id": item_id,
            "parent_item_id": self._outer_action_id,
            "revision": revision,
            "payload": payload,
        }

    @staticmethod
    def _text(value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()[:1000]


__all__ = ["ResearchTimelineProjector"]
