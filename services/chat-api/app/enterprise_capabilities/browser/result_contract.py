"""Stable, compact result contract for the DSH browser tool."""

from __future__ import annotations

from collections import Counter, deque
from typing import Any


_PROJECTABLE_EVENTS = {"intervention_required", "subagent_done", "runtime_status", "answer"}
_SUCCESS = {"succeeded", "completed", "done", "partial_success"}
_SUSPENDED = {"suspended_waiting_approval", "intervention_required"}


class BrowserResultEventAccumulator:
    """Keep result metadata bounded while progress is streamed elsewhere."""

    def __init__(self, max_events: int = 20) -> None:
        self._max_events = max(1, int(max_events))
        self._counts: Counter[str] = Counter()
        self._relevant: deque[dict[str, Any]] = deque(maxlen=self._max_events)
        self._latest: dict[str, dict[str, Any]] = {}

    def record(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("type") or "unknown")
        self._counts[event_type] += 1
        if event_type in _PROJECTABLE_EVENTS:
            copied = dict(event)
            self._relevant.append(copied)
            self._latest[event_type] = copied

    @property
    def events(self) -> list[dict[str, Any]]:
        pinned = [
            self._latest[event_type]
            for event_type in ("intervention_required", "subagent_done")
            if event_type in self._latest
        ]
        recent = [event for event in self._relevant if event not in pinned]
        return recent[-max(0, self._max_events - len(pinned)):] + pinned

    @property
    def event_counts(self) -> dict[str, int]:
        return dict(self._counts)

    def latest(self, event_type: str) -> dict[str, Any]:
        return dict(self._latest.get(event_type) or {})


def _summary(artifacts: dict[str, Any], status: str) -> str:
    browser_result = artifacts.get("browser_result")
    if isinstance(browser_result, dict) and str(browser_result.get("summary") or "").strip():
        return str(browser_result["summary"]).strip()
    receipt = artifacts.get("browser_receipt")
    if isinstance(receipt, dict):
        for key in ("summary", "reason", "error"):
            if str(receipt.get(key) or "").strip():
                return str(receipt[key]).strip()
    if status in _SUSPENDED:
        return "Browser needs human assistance. Stop this turn and wait for the user to resume it."
    return "Browser task completed." if status in _SUCCESS else "Browser task did not complete."


def build_browser_tool_result(
    *,
    operation: str,
    status: str,
    artifacts: dict[str, Any],
    events: list[dict[str, Any]],
    event_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    suspended = status in _SUSPENDED
    successful = status in _SUCCESS
    relevant_events = [
        event for event in events
        if isinstance(event, dict) and str(event.get("type") or "") in _PROJECTABLE_EVENTS
    ][-20:]
    result: dict[str, Any] = {
        "success": suspended or successful,
        "status": status,
        "operation": operation,
        "responseSummary": _summary(artifacts, status),
        "artifacts": artifacts,
        "domain_events": relevant_events,
        "event_counts": (
            dict(event_counts)
            if event_counts is not None
            else dict(Counter(str(event.get("type") or "unknown") for event in events))
        ),
    }
    intervention = artifacts.get("intervention_suspension")
    if isinstance(intervention, dict) and intervention:
        result["intervention_suspension"] = intervention
    if not result["success"]:
        result["message"] = result["responseSummary"]
    return result


__all__ = ["BrowserResultEventAccumulator", "build_browser_tool_result"]
