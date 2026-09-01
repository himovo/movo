from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterable


def _event_type(event: dict[str, Any]) -> str:
    return str(event.get("type") or event.get("event_type") or "").strip()


def _content(event: dict[str, Any]) -> Any:
    return event.get("content", event.get("payload"))


@dataclass
class ScenarioResult:
    events: list[dict[str, Any]] = field(default_factory=list)
    malformed_lines: list[str] = field(default_factory=list)
    task_ir: dict[str, Any] = field(default_factory=dict)
    task_contract: dict[str, Any] = field(default_factory=dict)
    answers: list[str] = field(default_factory=list)
    documents: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    node_starts: list[dict[str, Any]] = field(default_factory=list)
    node_completions: list[dict[str, Any]] = field(default_factory=list)
    terminal_status: str = "unknown"

    @property
    def final_text(self) -> str:
        return "\n".join(text for text in self.answers if text.strip())

    @property
    def event_types(self) -> list[str]:
        return [_event_type(event) for event in self.events]


class EventCollector:
    async def collect(self, stream: AsyncIterable[str | bytes | dict[str, Any]]) -> ScenarioResult:
        result = ScenarioResult()
        async for raw in stream:
            for event in self._decode(raw, result):
                self._record(event, result)
        return result

    @staticmethod
    def _decode(
        raw: str | bytes | dict[str, Any], result: ScenarioResult
    ) -> list[dict[str, Any]]:
        if isinstance(raw, dict):
            return [raw]
        text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        events: list[dict[str, Any]] = []
        for line in text.splitlines():
            candidate = line.strip()
            if not candidate:
                continue
            if candidate.startswith("data:"):
                candidate = candidate[5:].strip()
            try:
                decoded = json.loads(candidate)
            except json.JSONDecodeError:
                result.malformed_lines.append(candidate)
                continue
            if isinstance(decoded, dict):
                events.append(decoded)
        return events

    @staticmethod
    def _record(event: dict[str, Any], result: ScenarioResult) -> None:
        result.events.append(event)
        event_type = _event_type(event)
        content = _content(event)

        if event_type == "runtime_status" and isinstance(content, dict):
            if isinstance(content.get("task_ir"), dict):
                result.task_ir = dict(content["task_ir"])
            if isinstance(content.get("task_contract"), dict):
                result.task_contract = dict(content["task_contract"])
            state = str(content.get("state") or content.get("status") or "").lower()
            if state:
                result.terminal_status = state
        elif event_type == "answer":
            if isinstance(content, str):
                result.answers.append(content)
            elif isinstance(content, dict):
                text = str(content.get("text") or content.get("answer") or "")
                if text:
                    result.answers.append(text)
        elif event_type in {"document", "artifact"} and isinstance(content, dict):
            result.documents.append(dict(content))
        elif event_type in {"tool_call", "tool.started", "tool_start"}:
            result.tool_calls.append(dict(content) if isinstance(content, dict) else {"name": str(content or "")})
        elif event_type in {"node_start", "node.started"}:
            result.node_starts.append(dict(content) if isinstance(content, dict) else {"node_id": str(content or "")})
        elif event_type in {"node_complete", "node.completed"}:
            result.node_completions.append(dict(content) if isinstance(content, dict) else {"node_id": str(content or "")})
        elif event_type == "activity" and isinstance(content, dict):
            kind = str(content.get("kind") or "")
            if kind == "tool":
                result.tool_calls.append({"name": str(content.get("detail") or "")})
            elif kind == "complete":
                result.terminal_status = "completed"
            elif kind == "error":
                result.terminal_status = "failed"
        elif event_type in {"error", "graph.failed"}:
            result.terminal_status = "failed"

        if event_type in {"complete", "task.completed", "graph.completed"}:
            result.terminal_status = "completed"
