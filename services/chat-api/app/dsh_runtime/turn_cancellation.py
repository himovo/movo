"""User-requested DSH turn cancellation coordination."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from app.dsh_runtime.bindings import KernelBindingRepository
from app.dsh_runtime.contracts import CancelSessionRequest
from app.dsh_runtime.conversation import ConversationRepository
from app.dsh_runtime.errors import DshRuntimeError
from app.dsh_runtime.gateway import DshAgentKernelGateway
from app.dsh_runtime.runtime_coordinator import RuntimeCoordinator
from app.dsh_runtime.turn_finalization import TurnStateFinalizer
from app.dsh_runtime.turn_recovery import TurnTerminalRecovery


class TurnCancellationCoordinator:
    """Wait for DSH quiescence, then release both persisted product states."""

    def __init__(
        self,
        *,
        gateway: DshAgentKernelGateway,
        runtime_coordinator: RuntimeCoordinator,
        conversations: ConversationRepository,
        bindings: KernelBindingRepository,
        recovery: TurnTerminalRecovery,
        task_for_message: Callable[[str], asyncio.Task[str] | None],
    ) -> None:
        self._gateway = gateway
        self._runtime_coordinator = runtime_coordinator
        self._conversations = conversations
        self._bindings = bindings
        self._recovery = recovery
        self._task_for_message = task_for_message
        self._finalizer = TurnStateFinalizer(bindings, conversations)

    async def cancel(self, conversation_id: str, *, tenant_id: str, user_id: str) -> bool:
        conversation = await self._conversations.owned(
            conversation_id, tenant_id=tenant_id, user_id=user_id
        )
        binding = await self._bindings.current(
            conversation_id, tenant_id=tenant_id, user_id=user_id
        )
        if binding is None:
            return False
        active = dict(binding.get("active_turn") or {})
        message_id = str(active.get("message_id") or "")
        active_status = str(active.get("status") or "")
        if not message_id:
            return await self._clear_orphan_sidebar_run(
                conversation, conversation_id=conversation_id,
                tenant_id=tenant_id, user_id=user_id,
            )
        if active_status in {"completed", "failed", "cancelled"}:
            await self._finalizer.finalize(
                binding=binding, message_id=message_id, status=active_status
            )
            return True

        binding = await self._runtime_coordinator.restore(binding)
        cancellation = await self._gateway.cancel(
            CancelSessionRequest(
                session_id=str(binding["kernel_session_id"]), cause="user_cancelled"
            )
        )
        if cancellation.get("turnPending") or cancellation.get("jobsPending"):
            raise DshRuntimeError("DSH turn is still stopping; retry cancellation shortly")

        task = self._task_for_message(message_id)
        if task is not None:
            await self._settle_local_runner(task, binding=binding, message_id=message_id)
        else:
            await self._recovery.ingest_once(binding=binding, message_id=message_id)
        await self._finalize_if_still_running(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            user_id=user_id,
            message_id=message_id,
        )
        return True

    async def _settle_local_runner(
        self, task: asyncio.Task[str], *, binding: dict[str, Any], message_id: str
    ) -> None:
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=10.0)
        except asyncio.TimeoutError:
            await self._recovery.ingest_once(binding=binding, message_id=message_id)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _finalize_if_still_running(
        self,
        *,
        conversation_id: str,
        tenant_id: str,
        user_id: str,
        message_id: str,
    ) -> None:
        current = await self._bindings.current(
            conversation_id, tenant_id=tenant_id, user_id=user_id
        )
        active = dict((current or {}).get("active_turn") or {})
        if (
            current is not None
            and str(active.get("message_id") or "") == message_id
            and str(active.get("status") or "") not in {"completed", "failed", "cancelled"}
        ):
            await self._finalizer.finalize(
                binding=current, message_id=message_id, status="cancelled"
            )

    async def _clear_orphan_sidebar_run(
        self,
        conversation: dict[str, Any],
        *,
        conversation_id: str,
        tenant_id: str,
        user_id: str,
    ) -> bool:
        message_id = str((conversation.get("active_run") or {}).get("message_id") or "")
        if not message_id:
            return False
        await self._conversations.clear_active_run(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            user_id=user_id,
            message_id=message_id,
        )
        return True
