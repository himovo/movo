"""Durable terminal-event recovery for DSH turns."""

from __future__ import annotations

from typing import Any

from app.dsh_runtime.bindings import KernelBindingRepository
from app.dsh_runtime.conversation import ConversationRepository
from app.dsh_runtime.errors import DshNotFoundError
from app.dsh_runtime.event_mapper import DshEventMapper
from app.dsh_runtime.events import KernelEventRepository, KernelEventWrite
from app.dsh_runtime.events.authoritative_delivery import (
    AuthoritativeDeliveryGuard,
    DeliveryStore,
)
from app.dsh_runtime.events.tool_presentation import tool_presentations
from app.dsh_runtime.gateway import DshAgentKernelGateway
from app.dsh_runtime.profile.service import RuntimeProfilePublisher
from app.dsh_runtime.runtime_coordinator import RuntimeCoordinator
from app.dsh_runtime.turn_finalization import (
    TurnAssistantProjection,
    TurnStateFinalizer,
)


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
        self._coordinator = RuntimeCoordinator(gateway, bindings)

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
        browser_intervention = self._browser_intervention(rows)
        await self._finalizer.finalize(
            binding=binding,
            message_id=message_id,
            status=terminal_status,
            clear_conversation=not (
                terminal_status == "completed" and browser_intervention is not None
            ),
            intervention=browser_intervention,
            assistant=TurnAssistantProjection(
                content=self._assistant_text(rows),
                execution_events=self._compact_history_events(rows),
            ),
        )
        return True

    async def reconcile_all_active_claims(self) -> int:
        """Sweep every running durable claim after a process restart.

        The sweep predicate is exactly ``{"current": true,
        "active_turn.claim_state": "running", "active_turn.status":
        "running"}``: ``status`` is required alongside ``claim_state``
        because ``finish_turn()`` filters on ``active_turn.status``, so a
        claim_state-only predicate would re-sweep historical bindings. Each
        claim is rehydrated through ``RuntimeCoordinator.restore()`` BEFORE
        ``ingest_once()`` — the in-process session registry starts empty, so
        ingest-first would raise ``DshNotFoundError`` for every claim.
        Returns the number of claims that reached a terminal state.
        """
        return await self._reconcile_claims(conversation_id=None)

    async def reconcile_session_claims(self, conversation_id: str) -> int:
        """Converge one session's running claims without waiting for restart."""
        return await self._reconcile_claims(conversation_id=conversation_id)

    async def _reconcile_claims(self, *, conversation_id: str | None) -> int:
        finalized = 0
        for binding in await self._running_claims(conversation_id=conversation_id):
            if await self._reconcile_claim(binding):
                finalized += 1
        return finalized

    async def _running_claims(
        self, *, conversation_id: str | None
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {
            "current": True,
            "active_turn.claim_state": "running",
            "active_turn.status": "running",
        }
        if conversation_id:
            query["conversation_id"] = conversation_id
        collection = self._bindings._collection
        return [row async for row in collection.find(query)]

    async def _reconcile_claim(self, binding: dict[str, Any]) -> bool:
        message_id = str((binding.get("active_turn") or {}).get("message_id") or "")
        try:
            binding = await self._coordinator.restore(binding)
        except Exception:
            # Process-local miss or transport/timeout: retry next sweep pass,
            # never finalize on an unproven session.
            return False
        if not message_id:
            return False
        try:
            await self.ingest_once(binding=binding, message_id=message_id)
        except DshNotFoundError:
            # The host definitively reports no such session AFTER a
            # successful restore: the claim is orphaned and finalization is
            # the only way a restart avoids a permanent 409.
            try:
                return await self._finalize_orphaned_claim(binding, message_id)
            except Exception:
                return False
        except Exception:
            return False
        return True

    async def _finalize_orphaned_claim(
        self, binding: dict[str, Any], message_id: str
    ) -> bool:
        tenant_id = str(binding["tenant_id"])
        user_id = str(binding["user_id"])
        history_rows: list[dict[str, Any]] = []
        message = await self._conversations.message(
            message_id, tenant_id=tenant_id, user_id=user_id
        )
        if message is not None:
            failure = DshEventMapper(
                kernel_version=str(binding.get("kernel_version") or "0.1.0-rc.6")
            ).runtime_failure(
                runtime_id=str(binding["runtime_id"]),
                session_id=str(binding["kernel_session_id"]),
                profile_version=str(binding["profile_version"]),
                cursor=9_200_000_000_000_000,
                message="DSH runtime reports no session for the claimed turn",
            )
            await self._events.persist_batch(
                [
                    KernelEventWrite(
                        event=failure,
                        projected=self._events.project(failure, message_id=message_id),
                    )
                ],
                tenant_id=tenant_id,
                user_id=user_id,
                conversation_id=str(binding["conversation_id"]),
                message_id=message_id,
            )
            rows = await self._events.all_for_message(
                message_id, tenant_id=tenant_id, user_id=user_id
            )
            history_rows = self._compact_history_events(rows)
        await self._finalizer.finalize(
            binding=binding,
            message_id=message_id,
            status="failed",
            assistant=TurnAssistantProjection(content="", execution_events=history_rows),
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
