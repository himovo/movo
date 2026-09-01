from __future__ import annotations

import asyncio
from typing import Any

from .contracts import PresentationJobSnapshot
from .repository import PresentationJobRepository


class PresentationExecutionSession:
    """Small pipeline-facing facade; persistence details stay out of planners."""

    def __init__(
        self,
        repository: PresentationJobRepository,
        snapshot: PresentationJobSnapshot,
        *,
        action_id: str,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        self._repository = repository
        self._snapshot = snapshot
        self.action_id = action_id
        self.cancel_event = cancel_event

    @property
    def job_id(self) -> str:
        return self._snapshot.job_id

    @property
    def continuation_token(self) -> str:
        return self._snapshot.continuation_token

    @property
    def story_plan(self) -> dict[str, Any]:
        return dict(self._snapshot.story_plan or {})

    @property
    def planning(self) -> dict[str, Any]:
        return dict(self._snapshot.planning or {})

    @property
    def pages(self) -> dict[str, dict[str, Any]]:
        return {str(key): dict(value) for key, value in dict(self._snapshot.pages or {}).items()}

    def raise_if_cancelled(self) -> None:
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise asyncio.CancelledError("presentation generation cancelled")

    async def stage(self, value: str) -> None:
        self.raise_if_cancelled()
        await self._repository.save_stage(self.job_id, self.action_id, value)

    async def checkpoint_story(self, payload: dict[str, Any]) -> None:
        self.raise_if_cancelled()
        await self._repository.save_story_plan(self.job_id, self.action_id, payload)
        self._snapshot.story_plan = dict(payload)

    async def checkpoint_planning(self, payload: dict[str, Any]) -> None:
        self.raise_if_cancelled()
        await self._repository.save_planning(self.job_id, self.action_id, payload)
        self._snapshot.planning = dict(payload)

    async def checkpoint_page(
        self,
        page_id: str,
        payload: dict[str, Any],
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.raise_if_cancelled()
        checkpoint = {"blueprint": dict(payload), "metadata": dict(metadata or {})}
        await self._repository.save_page(self.job_id, self.action_id, page_id, checkpoint)
        self._snapshot.pages[str(page_id).replace(".", "_")] = checkpoint


__all__ = ["PresentationExecutionSession"]
