"""Settle browser suspension claims from the owned DSH turn lifecycle."""

from __future__ import annotations

import asyncio
import logging

from app.governance.suspensions import suspension_service


logger = logging.getLogger(__name__)
_watchers: set[asyncio.Task[None]] = set()


def schedule_browser_resume(*, chat_service, message_id: str, suspension_id: str, user_id: str) -> None:
    async def settle() -> None:
        status = await chat_service.wait_turn(message_id)
        if status == "completed":
            await suspension_service.complete_resume(suspension_id=suspension_id, user_id=user_id)
        else:
            await suspension_service.fail_resume(
                suspension_id=suspension_id, user_id=user_id, error=f"dsh_turn_{status}"
            )

    task = asyncio.create_task(settle(), name=f"dsh-browser-resume:{suspension_id}")
    _watchers.add(task)

    def done(finished: asyncio.Task[None]) -> None:
        _watchers.discard(finished)
        try:
            finished.result()
        except Exception:
            logger.exception("DSH browser resume settlement failed", extra={"suspension_id": suspension_id})

    task.add_done_callback(done)
