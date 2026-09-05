"""Durable terminal-event recovery for DSH turns."""

from __future__ import annotations

from typing import Any

from app.dsh_runtime.bindings import KernelBindingRepository
from app.dsh_runtime.conversation import ConversationRepository
from app.dsh_runtime.events import KernelEventRepository, KernelEventWrite
from app.dsh_runtime.events.authoritative_delivery import (
    AuthoritativeDeliveryGuard,
    DeliveryStore,
)
from app.dsh_runtime.events.tool_presentation import tool_presentations
from app.dsh_runtime.gateway import DshAgentKernelGateway
from app.dsh_runtime.profile.service import RuntimeProfilePublisher
from app.dsh_runtime.turn_finalization import TurnStateFinalizer


class TurnTerminalRecovery:
    """Reconcile product state only from authoritative persisted terminal events."""

    def __init__(
        self,
        *,
        gateway: DshAgentKernelGateway,
        conversations: ConversationRepository,
        bindings: KernelBindingRepository,
        events: KernelEventRepository,
        profiles: RuntimeProfilePublisher,
        authoritative_deliveries: DeliveryStore | None = None,
    ) -> None:
        self._gateway = gateway
        self._conversations = conversations
        self._bindings = bindings
        self._events = events
        self._profiles = profiles
        self._authoritative_deliveries = authoritative_deliveries
        self._finalizer = TurnStateFinalizer(bindings, conversations)

    async def ingest_once(self, *, binding: dict[str, Any], message_id: str) -> None:
        native_events = await self._gateway.events_once(
            str(binding["kernel_session_id"]), int(binding.get("event_cursor") or 0)
        )
        writes: list[KernelEventWrite] = []
        profile = await self._profiles.get(str(binding["profile_version"]))
        tool_ui = tool_presentations(profile)
        delivery_guard = AuthoritativeDeliveryGuard(
            store=self._authoritative_deliveries,
            tool_presentations=tool_ui,
            tenant_id=str(binding["tenant_id"]),
            user_id=str(binding["user_id"]),
            message_id=message_id,
        )
        for event in native_events:
            projected = self._events.project(
                event, message_id=message_id, tool_presentations=tool_ui
            )
            projected = await delivery_guard.apply(event, projected)
            writes.append(KernelEventWrite(event=event, projected=projected))
        if writes:
            await self._events.persist_batch(
                writes,
                tenant_id=str(binding["tenant_id"]),
                user_id=str(binding["user_id"]),
                conversation_id=str(binding["conversation_id"]),
                message_id=message_id,
            )
            await self._bindings.advance_cursor(
                str(binding["binding_id"]), max(write.event.cursor for write in writes)
            )
        await self.finalize_persisted_terminal(binding=binding, message_id=message_id)

    async def finalize_persisted_terminal(
        self, *, binding: dict[str, Any], message_id: str
    ) -> bool:
        rows = await self._events.all_for_message(
            message_id,
            tenant_id=str(binding["tenant_id"]),
            user_id=str(binding["user_id"]),
        )
        terminal = next(
            (
                row
                for row in reversed(rows)
                if row.get("type") in {"run.completed", "run.failed", "run.cancelled"}
            ),
            None,
        )
        if terminal is None:
            return False

        terminal_status = str(terminal["type"]).removeprefix("run.")
        assistant_text = self._assistant_text(rows)
        await self._conversations.update_assistant_projection(
            message_id=message_id,
            tenant_id=str(binding["tenant_id"]),
            user_id=str(binding["user_id"]),
            content=assistant_text,
            execution_events=self._compact_history_events(rows),
        )
        browser_intervention = self._browser_intervention(rows)
        await self._finalizer.finalize(
            binding=binding,
            message_id=message_id,
            status=terminal_status,
            clear_conversation=not (
                terminal_status == "completed" and browser_intervention is not None
            ),
        )
        if terminal_status == "completed" and browser_intervention is not None:
            await self._conversations.suspend_active_run(
                conversation_id=str(binding["conversation_id"]),
                tenant_id=str(binding["tenant_id"]),
                user_id=str(binding["user_id"]),
                message_id=message_id,
                intervention=browser_intervention,
            )
        return True

    async def recover(self, binding: dict[str, Any]) -> dict[str, Any]:
        """Repair a stale lock only when its durable event log proves termination."""

        message_id = str((binding.get("active_turn") or {}).get("message_id") or "")
        if not message_id:
            return binding
        try:
            await self.finalize_persisted_terminal(binding=binding, message_id=message_id)
            current = await self._bindings.current(
                str(binding["conversation_id"]),
                tenant_id=str(binding["tenant_id"]),
                user_id=str(binding["user_id"]),
            )
            return current or binding
        except Exception:
            return binding

    @staticmethod
    def _assistant_text(rows: list[dict[str, Any]]) -> str:
        value = ""
        for row in rows:
            if row.get("item_kind") != "final_answer":
                continue
            text = str((row.get("payload") or {}).get("text") or "")
            value = text if row.get("type") == "item.completed" else value + text
        return value

    @staticmethod
    def _compact_history_events(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [row for row in rows if row.get("type") != "item.delta"]

    @staticmethod
    def _browser_intervention(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        for row in reversed(rows):
            candidate = (row.get("payload") or {}).get("browser_intervention")
            if isinstance(candidate, dict) and candidate.get("suspension_id"):
                return dict(candidate)
        return None
