"""Classify DSH assistant replies using the following turn boundary."""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.dsh_runtime.contracts import KernelEventEnvelope
from app.dsh_runtime.events.projection import KernelEventProjector


class TurnReplyBuffer:
    """Hold a text-only reply until DSH reveals whether the turn continues."""

    def __init__(self) -> None:
        self._pending: list[KernelEventEnvelope] = []

    def push(self, event: KernelEventEnvelope) -> list[tuple[KernelEventEnvelope, str | None]]:
        if not self._pending:
            if self._is_candidate(event):
                self._pending.append(event)
                return []
            return [(event, None)]

        if not self._decides(event):
            self._pending.append(event)
            return []

        final = event.type == "turn.completed" and self._turn_succeeded(event)
        kind = "final_answer" if final else "commentary"
        ready = [(self._pending[0], kind)]
        ready.extend((held, None) for held in self._pending[1:])
        self._pending.clear()
        ready.extend(self.push(event))
        return ready

    def drain(self) -> list[tuple[KernelEventEnvelope, str | None]]:
        if not self._pending:
            return []
        ready = [(self._pending[0], "commentary")]
        ready.extend((held, None) for held in self._pending[1:])
        self._pending.clear()
        return ready

    @staticmethod
    def _is_candidate(event: KernelEventEnvelope) -> bool:
        if event.type != "agent.message.completed":
            return False
        return bool(KernelEventProjector._message_text(event.payload).strip()) and not KernelEventProjector._message_has_tool_call(event.payload)

    @staticmethod
    def _turn_succeeded(event: KernelEventEnvelope) -> bool:
        reason = event.payload.get("reason")
        kind = str(reason.get("kind") if isinstance(reason, dict) else reason or "stop")
        return kind not in {"aborted", "cancelled", "user", "error"}

    @staticmethod
    def _decides(event: KernelEventEnvelope) -> bool:
        return event.type in {
            "turn.completed", "turn.started", "runtime.failed", "model.request.failed",
            "tool.call.started", "tool.call.completed", "agent.step.started",
            "agent.message.completed", "agent.message.delta",
        }


async def classified_turn_events(
    source: AsyncIterator[KernelEventEnvelope], attach_after: int,
) -> AsyncIterator[tuple[KernelEventEnvelope, str | None]]:
    buffer = TurnReplyBuffer()
    async for event in source:
        if event.cursor <= attach_after:
            yield event, None
            continue
        for ready in buffer.push(event):
            yield ready
    for ready in buffer.drain():
        yield ready
