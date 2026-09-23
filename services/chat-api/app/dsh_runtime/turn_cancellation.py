"""User-requested DSH turn cancellation coordination."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from bson import ObjectId

from app.dsh_runtime.bindings import KernelBindingRepository
from app.dsh_runtime.contracts import CancelSessionRequest
from app.dsh_runtime.conversation import ConversationRepository
from app.dsh_runtime.conversation.participants_repository import (
    SessionParticipantsRepository,
)
from app.dsh_runtime.errors import DshRuntimeError
from app.dsh_runtime.gateway import DshAgentKernelGateway
from app.dsh_runtime.runtime_coordinator import RuntimeCoordinator
from app.dsh_runtime.turn_finalization import TurnStateFinalizer
from app.dsh_runtime.turn_recovery import TurnTerminalRecovery


class CancelNotAllowedError(PermissionError):
    """A conversation member who did not initiate the run tried to cancel it.

    Cancel is initiator-only (session-sharing plan todo 15): every other
    member - including the session owner when they did not initiate that
    run - is denied, and a run with no recorded initiator (a legacy row)
    fails closed. Carries a stable ``code`` so the endpoint layer maps it
    to 403 (todo 29's frontend stop-control consumes it).
    """

    code = "session_cancel_initiator_required"

    def __init__(self, *, conversation_id: str, reason: str) -> None:
        self.conversation_id = conversation_id
        self.reason = reason
        super().__init__(
            f"only the run's initiator may cancel conversation"
            f" {conversation_id}: {reason}"
        )


async def member_conversation(
    db: Any,
    participants: SessionParticipantsRepository,
    conversation_id: str,
    *,
    tenant_id: str,
    user_id: str,
) -> dict[str, Any]:
    """Membership + visibility gate for cancel (session-sharing plan todo 15).

    Membership = the session owner OR an active participant row (the plan's
    definition; owners never hold a participant row). Denials: unknown id /
    cross-tenant / never-a-member -> LookupError (404 cannot-see at the
    endpoint, todo 4's status matrix; T14's fail-closed pin relies on this
    denial form); a removed participant row -> CancelNotAllowedError (403,
    the membership gate denies them even for their own in-flight run).
    """
    if not ObjectId.is_valid(conversation_id):
        raise LookupError("conversation_not_found")
    session = await db.chat_sessions.find_one(
        {"_id": ObjectId(conversation_id), "main_id": tenant_id}
    )
    if session is None:
        raise LookupError("conversation_not_found")
    if str(session.get("user_id") or "") == user_id:
        return session
    if await participants.is_member(conversation_id, tenant_id=tenant_id, user_id=user_id):
        return session
    removed = await participants.list(
        conversation_id, tenant_id=tenant_id, include_removed=True
    )
    if any(str(row.get("user_id") or "") == user_id for row in removed):
        raise CancelNotAllowedError(
            conversation_id=conversation_id,
            reason="the caller is no longer an active member of this conversation",
        )
    raise LookupError("conversation_not_found")


def assert_run_initiator(
    conversation: dict[str, Any], *, conversation_id: str, user_id: str
) -> None:
    """The initiator-identity check (session-sharing plan todo 15).

    The initiator source is T14's ``active_run.initiator_user_id``
    (``mark_active_run`` records the caller). A run with NO recorded
    initiator (a legacy row) FAILS CLOSED: every member is denied. When
    nothing is recorded to cancel (no ``active_run`` at all) the check is
    skipped - the no-op paths keep today's behaviour.
    """
    active_run = dict(conversation.get("active_run") or {})
    if not active_run:
        return
    initiator = str(active_run.get("initiator_user_id") or "")
    if not initiator:
        raise CancelNotAllowedError(
            conversation_id=conversation_id,
            reason="the run has no recorded initiator",
        )
    if initiator != user_id:
        raise CancelNotAllowedError(
            conversation_id=conversation_id,
            reason="the caller did not initiate this run",
        )


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
        try:
            conversation = await self._conversations.owned(
                conversation_id, tenant_id=tenant_id, user_id=user_id
            )
        except LookupError:
            # Session-sharing plan todo 15: the owner-only owned() denial is
            # no longer final - resolve through the membership gate. A member
            # (active participant) proceeds to the initiator-identity check;
            # a removed member is denied (CancelNotAllowedError, 403 at the
            # endpoint); a never-a-member keeps the LookupError (404
            # cannot-see, todo 4's matrix). The db comes from the
            # conversations repo's own collection - this module takes no
            # get_db seam and the runtime callers pass real repos.
            db = self._conversations._sessions.database
            conversation = await member_conversation(
                db,
                SessionParticipantsRepository(db),
                conversation_id,
                tenant_id=tenant_id,
                user_id=user_id,
            )
        assert_run_initiator(conversation, conversation_id=conversation_id, user_id=user_id)
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
