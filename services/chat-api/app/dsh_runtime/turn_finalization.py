"""Idempotent terminal-state projection shared by every DSH turn exit path."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.dsh_runtime.bindings import KernelBindingRepository
from app.dsh_runtime.conversation import ConversationRepository


class TurnFinalizationRetryableError(RuntimeError):
    """A coordination step failed before any product state moved.

    The coordinator runs its steps in order and raises this BEFORE the
    binding transition and the active_run clear/suspend, so a retry resumes
    from the already-durable steps and never double-writes terminal state.
    """

    code = "turn_finalization_retryable"
    retryable = True


@dataclass(frozen=True)
class TurnAssistantProjection:
    content: str
    execution_events: list[dict[str, Any]]
    evidence_bundles: list[dict[str, Any]] | None = None


class TurnStateFinalizer:
    """The sole terminal-completion coordinator for every DSH turn exit path.

    ``clear_conversation=True`` order: (1) persist and flush the sequenced
    terminal event, (2) persist the assistant projection, (3) transition the
    binding to terminal, (4) clear the session ``active_run``.
    ``clear_conversation=False`` (browser-intervention suspension) performs
    steps 1-3 and then suspends the run, intentionally retaining
    ``active_run``.
    """

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
        intervention: dict[str, Any] | None = None,
        flush: Callable[[], Awaitable[None]] | None = None,
        assistant: TurnAssistantProjection | None = None,
    ) -> None:
        if status not in {"completed", "failed", "cancelled"}:
            raise ValueError(f"unsupported terminal DSH turn status: {status}")

        if flush is not None:
            await self._step(flush, "persist and flush the terminal event")
        if assistant is not None:
            await self._step(
                lambda: self._conversations.update_assistant_projection(
                    message_id=message_id,
                    tenant_id=str(binding["tenant_id"]),
                    user_id=str(binding["user_id"]),
                    content=assistant.content,
                    execution_events=list(assistant.execution_events),
                    evidence_bundles=(
                        None
                        if assistant.evidence_bundles is None
                        else list(assistant.evidence_bundles)
                    ),
                ),
                "persist the assistant projection",
            )
        await self._step(
            lambda: self._finish_binding(binding, message_id, status),
            "transition the binding to terminal",
        )
        if clear_conversation:
            await self._step(
                lambda: self._conversations.clear_active_run(
                    conversation_id=str(binding["conversation_id"]),
                    tenant_id=str(binding["tenant_id"]),
                    user_id=str(binding["user_id"]),
                    message_id=message_id,
                ),
                "clear the session active_run",
            )
        elif intervention is not None:
            await self._step(
                lambda: self._conversations.suspend_active_run(
                    conversation_id=str(binding["conversation_id"]),
                    tenant_id=str(binding["tenant_id"]),
                    user_id=str(binding["user_id"]),
                    message_id=message_id,
                    intervention=intervention,
                ),
                "suspend the session active_run",
            )

    async def _finish_binding(
        self, binding: dict[str, Any], message_id: str, status: str
    ) -> None:
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

    @staticmethod
    async def _step(step: Callable[[], Awaitable[None]], description: str) -> None:
        try:
            await step()
        except TurnFinalizationRetryableError:
            raise
        except Exception as exc:
            raise TurnFinalizationRetryableError(
                f"DSH turn finalization step failed: {description}"
            ) from exc
