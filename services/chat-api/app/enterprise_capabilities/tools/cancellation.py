from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ActiveCapabilityExecution:
    conversation_id: str
    cancel_event: asyncio.Event
    task: asyncio.Task[Any]


class ActiveCapabilityExecutions:
    """Process-local bridge from MOVO chat cancellation to Tool execution."""

    def __init__(self) -> None:
        self._items: dict[str, ActiveCapabilityExecution] = {}

    def register(self, action_id: str, conversation_id: str) -> asyncio.Event:
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("enterprise capability execution has no owning task")
        cancel_event = asyncio.Event()
        self._items[action_id] = ActiveCapabilityExecution(
            conversation_id=conversation_id,
            cancel_event=cancel_event,
            task=task,
        )
        return cancel_event

    def unregister(self, action_id: str) -> None:
        self._items.pop(action_id, None)

    def cancel_conversation(self, conversation_id: str) -> int:
        cancelled = 0
        for execution in list(self._items.values()):
            if execution.conversation_id != conversation_id:
                continue
            execution.cancel_event.set()
            if not execution.task.done():
                execution.task.cancel()
            cancelled += 1
        return cancelled


__all__ = ["ActiveCapabilityExecution", "ActiveCapabilityExecutions"]
