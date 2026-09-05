"""Idempotent terminal-state projection shared by every DSH turn exit path."""

from __future__ import annotations

from typing import Any

from app.dsh_runtime.bindings import KernelBindingRepository
from app.dsh_runtime.conversation import ConversationRepository


class TurnStateFinalizer:
    """Keep the admission lock and Conversation sidebar projection in sync."""

    def __init__(
        self,
        bindings: KernelBindingRepository,
        conversations: ConversationRepository,
    ) -> None:
        self._bindings = bindings
        self._conversations = conversations

    async def finalize(
        self,
        *,
        binding: dict[str, Any],
        message_id: str,
        status: str,
        clear_conversation: bool = True,
    ) -> None:
        if status not in {"completed", "failed", "cancelled"}:
            raise ValueError(f"unsupported terminal DSH turn status: {status}")

        transitioned = await self._bindings.finish_turn(
            str(binding["binding_id"]), message_id=message_id, status=status
        )
        if transitioned is False:
            current = await self._bindings.current(
                str(binding["conversation_id"]),
                tenant_id=str(binding["tenant_id"]),
                user_id=str(binding["user_id"]),
            )
            active = dict((current or {}).get("active_turn") or {})
            if (
                str(active.get("message_id") or "") == message_id
                and str(active.get("status") or "") not in {"completed", "failed", "cancelled"}
            ):
                raise RuntimeError("DSH turn admission lock is still active")
        if clear_conversation:
            await self._conversations.clear_active_run(
                conversation_id=str(binding["conversation_id"]),
                tenant_id=str(binding["tenant_id"]),
                user_id=str(binding["user_id"]),
                message_id=message_id,
            )
