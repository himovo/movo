"""Execute an authorized native DSH plugin command in a conversation claim."""

from __future__ import annotations

import logging
import asyncio
from datetime import datetime, timezone
from typing import Any

from app.dsh_runtime.bindings import KernelBindingRepository
from app.dsh_runtime.conversation import ConversationRepository
from app.dsh_runtime.events import KernelEventRepository, KernelEventWrite
from app.dsh_runtime.events.durable_writer import DurableKernelEventWriter
from app.dsh_runtime.events.live_stream import LiveTurnStream
from app.dsh_runtime.events.turn_channel import TurnEventRegistry
from app.dsh_runtime.gateway import DshAgentKernelGateway
from app.dsh_runtime.profile.plugin_command_selection import require_plugin_command
from app.dsh_runtime.turn_finalization import TurnAssistantProjection, TurnStateFinalizer


logger = logging.getLogger(__name__)


def _event(message_id: str, kind: str, payload: dict[str, Any], *, item_kind: str = "") -> dict[str, Any]:
    row: dict[str, Any] = {
        "v": 3,
        "event_id": f"plugin-command:{message_id}:{kind}",
        "id": f"plugin-command:{message_id}:{kind}",
        "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
        "type": kind,
        "revision": 1,
        "payload": payload,
    }
    if item_kind:
        row["item_kind"] = item_kind
        row["item_id"] = f"{message_id}:plugin-command"
    return row


class PluginCommandRunner:
    def __init__(
        self, *, gateway: DshAgentKernelGateway, conversations: ConversationRepository,
        bindings: KernelBindingRepository, events: KernelEventRepository,
        turn_events: TurnEventRegistry | None,
    ) -> None:
        self._gateway = gateway
        self._events = events
        self._turn_events = turn_events
        self._finalizer = TurnStateFinalizer(bindings, conversations)
        self._bindings = bindings

    async def run(
        self, *, binding: dict[str, Any], message_id: str, text: str,
        selected_command_id: str, live_stream: LiveTurnStream,
    ) -> str:
        session_id = str(binding["kernel_session_id"])
        writer = DurableKernelEventWriter(
            events=self._events, bindings=self._bindings,
            binding_id=str(binding["binding_id"]),
            tenant_id=str(binding["tenant_id"]), user_id=str(binding["user_id"]),
            conversation_id=str(binding["conversation_id"]), message_id=message_id,
        )
        status = "failed"
        answer = ""
        history: list[dict[str, Any]] = []
        writer_closed = False
        native_done = False
        defer_to_recovery = False
        try:
            await require_plugin_command(
                tenant_id=str(binding["tenant_id"]), user_id=str(binding["user_id"]),
                selected_id=selected_command_id,
            )
            before = await self._gateway.head_cursor(session_id)
            marked = await self._bindings.mark_plugin_command_head(
                str(binding["binding_id"]), message_id=message_id, native_cursor=before,
            )
            if not marked:
                raise RuntimeError("plugin command claim is no longer active")
            await self._publish(message_id, _event(message_id, "run.started", {"kernel": "dsh"}), live_stream)
            if self._turn_events:
                await self._turn_events.flush(message_id)
            execution = await self._gateway.execute_plugin_command(session_id, selected_command_id, text)
            native_done = True
            result = execution.get("result") or {}
            if not isinstance(result, dict):
                raise ValueError("DSH command returned an invalid result")
            status = "completed" if result.get("kind") == "success" else "failed"
            answer = str(result.get("text") or "")
            for event in await self._gateway.events_once(session_id, before):
                projected = self._events.project(event, message_id=message_id)
                if projected and projected.get("type") in {"run.started", "run.completed", "run.failed", "run.cancelled"}:
                    projected = None
                if projected:
                    projected = await self._publish(message_id, projected, live_stream, kernel=True)
                    history.append(projected)
                    if projected.get("type") == "item.completed" and projected.get("item_kind") == "final_answer":
                        answer = str((projected.get("payload") or {}).get("text") or answer)
                writer.enqueue(KernelEventWrite(event=event, projected=projected))
            await writer.close()
            writer_closed = True
        except BaseException as exc:
            status = "cancelled" if isinstance(exc, asyncio.CancelledError) else "failed"
            answer = str(exc) if not answer else answer
            defer_to_recovery = native_done
            if status == "failed":
                logger.exception("plugin command execution failed", extra={"message_id": message_id})
            if not writer_closed:
                await writer.abort()
        finally:
            try:
                if defer_to_recovery:
                    if self._turn_events:
                        await self._turn_events.abort(message_id)
                else:
                    if answer and not any(row.get("item_kind") == "final_answer" for row in history):
                        answer_row = await self._publish(
                            message_id, _event(message_id, "item.completed", {"text": answer, "provisional": False}, item_kind="final_answer"),
                            live_stream,
                        )
                        history.append(answer_row)
                    terminal = await self._publish(
                        message_id, _event(message_id, f"run.{status}", {"reason": "plugin_command"}),
                        live_stream,
                        publish_live=False,
                    )
                    history.append(terminal)
                    if self._turn_events:
                        await self._turn_events.finish(message_id)
                    await self._finalizer.finalize(
                        binding=binding, message_id=message_id, status=status,
                        assistant=TurnAssistantProjection(content=answer, execution_events=history),
                    )
                    live_stream.publish(terminal)
            finally:
                live_stream.finish()
        return "pending_recovery" if defer_to_recovery else status

    async def _publish(
        self, message_id: str, row: dict[str, Any], live_stream: LiveTurnStream,
        *, kernel: bool = False, publish_live: bool = True,
    ) -> dict[str, Any]:
        if self._turn_events is None:
            if publish_live:
                live_stream.publish(row)
            return row
        if kernel:
            return await self._turn_events.publish_kernel(message_id, row, publish_live=publish_live)
        return await self._turn_events.publish_standalone(
            message_id, row, publish_live=publish_live,
        ) or row
