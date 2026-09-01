"""Projection of native Browser Agent progress into ASKAI's stable V3 timeline."""

from __future__ import annotations

import re
from collections import defaultdict
from time import time
from typing import Any


class BrowserTimelineProjector:
    """Preserve producer-authored descriptions; own only IDs and lifecycle."""

    def __init__(
        self,
        *,
        outer_action_id: str,
        message_id: str = "",
        language: str = "zh",
    ) -> None:
        self._outer_action_id = outer_action_id
        self._event_namespace = f"{message_id or 'no-message'}:{outer_action_id}"
        self._language = "zh" if str(language or "").lower().startswith("zh") else "en"
        self._event_counter = 0
        self._tool_counter = 0
        self._active_tools: dict[str, list[tuple[str, str]]] = defaultdict(list)

    def project(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        event_type = str(event.get("type") or "").strip().lower()
        content = dict(event.get("content") or {}) if isinstance(event.get("content"), dict) else {}
        if event_type == "activity":
            if str(content.get("visibility") or "") == "debug":
                return []
            label = self._label(content.get("message"))
            if self._language == "zh" and not re.search(r"[\u4e00-\u9fff]", label):
                return []
            if not label:
                return []
            return [self._row(
                event_type="item.completed",
                item_id=self._new_item_id("activity"),
                revision=1,
                payload={
                    "label": label,
                    "category": "browser",
                    "source": "browser_agent",
                    "browser_activity_kind": str(content.get("kind") or ""),
                },
            )]
        if event_type == "tool_requested":
            # The rationale is model output from the Browser Agent. If it did
            # not describe the action, this adapter does not invent prose.
            if str(content.get("rationale_source") or "system") != "model":
                return []
            label = self._label(content.get("rationale"))
            if not label:
                return []
            tool_name = str(content.get("tool") or "")
            self._tool_counter += 1
            item_id = f"{self._outer_action_id}:browser-action:{self._tool_counter}"
            self._active_tools[tool_name].append((item_id, label))
            return [self._row(
                event_type="item.started",
                item_id=item_id,
                revision=1,
                payload={
                    "label": label,
                    "category": "browser",
                    "source": "browser_agent",
                    "browser_tool": tool_name,
                },
            )]
        if event_type == "tool_completed":
            tool_name = str(content.get("tool") or "")
            active = self._active_tools.get(tool_name)
            if not active:
                return []
            item_id, label = active.pop(0)
            ok = bool(content.get("ok"))
            payload = {
                "label": label,
                "category": "browser",
                "source": "browser_agent",
                "browser_tool": tool_name,
                "ok": ok,
            }
            if not ok and str(content.get("error") or "").strip():
                payload["error"] = str(content["error"])[:1000]
            return [self._row(
                event_type="item.completed" if ok else "item.failed",
                item_id=item_id,
                revision=2,
                payload=payload,
            )]
        if event_type == "intervention_required":
            suspension_id = str(content.get("suspension_id") or "").strip()
            if not suspension_id:
                return []
            return [self._row(
                event_type="item.started",
                item_kind="browser_handoff",
                item_id=f"browser-handoff:{suspension_id}",
                revision=1,
                payload={
                    **content,
                    "source": "browser_agent",
                    "status": "pending",
                },
            )]
        return []

    def _new_item_id(self, kind: str) -> str:
        self._event_counter += 1
        return f"{self._outer_action_id}:browser-{kind}:{self._event_counter}"

    def _row(
        self,
        *,
        event_type: str,
        item_id: str,
        revision: int,
        payload: dict[str, Any],
        item_kind: str = "activity",
    ) -> dict[str, Any]:
        self._event_counter += 1
        event_id = f"askai-v3:browser:{self._event_namespace}:{self._event_counter}"
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
    def _label(value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()[:240]


__all__ = ["BrowserTimelineProjector"]
