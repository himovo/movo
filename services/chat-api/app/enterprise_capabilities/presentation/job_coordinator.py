from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.enterprise_capabilities.runtime.contracts import CapabilityExecutionContext
from app.services.presentation.execution import (
    PresentationExecutionSession,
    PresentationJobRepository,
    build_presentation_job_identity,
)


@dataclass(frozen=True)
class PresentationJobOpenResult:
    session: PresentationExecutionSession | None
    terminal_result: dict[str, Any] | None


class PresentationJobCoordinator:
    """Connect DSH business calls to durable MOVO presentation jobs."""

    def __init__(self, repository: PresentationJobRepository | None = None) -> None:
        self.repository = repository or PresentationJobRepository()

    async def open(
        self,
        *,
        arguments: dict[str, Any],
        context: CapabilityExecutionContext,
        generation_mode: str,
    ) -> PresentationJobOpenResult:
        identity = build_presentation_job_identity(
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            conversation_id=context.conversation_id,
            message_id=context.message_id,
            generation_mode=generation_mode,
            arguments=arguments,
        )
        claim = await self.repository.claim(
            identity=identity,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            conversation_id=context.conversation_id,
            message_id=context.message_id,
            generation_mode=generation_mode,
            action_id=context.action_id,
        )
        snapshot = claim.snapshot
        if snapshot.status == "succeeded" and snapshot.final_result:
            return PresentationJobOpenResult(None, dict(snapshot.final_result))
        if snapshot.status == "cancelled":
            return PresentationJobOpenResult(
                None,
                self._terminal_rejection(
                    "PPT generation was cancelled by the user",
                    requested=int(arguments.get("page_count") or 0),
                    continuation_token=snapshot.continuation_token,
                ),
            )
        if not claim.acquired:
            return PresentationJobOpenResult(
                None,
                self._terminal_rejection(
                    "The same PPT job is already running; MOVO will not create a duplicate",
                    requested=int(arguments.get("page_count") or 0),
                    continuation_token=snapshot.continuation_token,
                ),
            )
        return PresentationJobOpenResult(
            PresentationExecutionSession(
                self.repository,
                snapshot,
                action_id=context.action_id,
                cancel_event=context.cancel_event,
            ),
            None,
        )

    async def complete(
        self,
        session: PresentationExecutionSession,
        result: dict[str, Any],
    ) -> None:
        await self.repository.complete(session.job_id, session.action_id, result)

    async def interrupt(self, session: PresentationExecutionSession, reason: str) -> None:
        await self.repository.interrupt(session.job_id, session.action_id, reason)

    async def fail(self, session: PresentationExecutionSession, reason: str) -> None:
        await self.repository.fail(session.job_id, session.action_id, reason)

    @staticmethod
    def _terminal_rejection(
        message: str,
        *,
        requested: int,
        continuation_token: str,
    ) -> dict[str, Any]:
        return {
            "success": False,
            "accepted": False,
            "acceptance": {
                "status": "rejected",
                "retry_allowed": False,
                "reasons": [message],
                "slide_count": 0,
                "requested_slide_count": requested,
                "editable": False,
            },
            "message": f"{message}. continuation_token={continuation_token}",
        }


__all__ = ["PresentationJobCoordinator", "PresentationJobOpenResult"]
