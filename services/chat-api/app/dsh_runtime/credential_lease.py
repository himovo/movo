"""Keep short-lived ASKAI gateway credentials valid for an active DSH turn."""
from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import Protocol


logger = logging.getLogger(__name__)


class CredentialRefresher(Protocol):
    async def refresh_session_credentials(self, session_id: str) -> None: ...


class KeyedAsyncLock:
    """Serialize refreshes for sessions sharing one immutable Runtime."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def for_key(self, key: str) -> asyncio.Lock:
        normalized = str(key)
        lock = self._locks.get(normalized)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[normalized] = lock
        return lock

    def discard(self, key: str) -> None:
        lock = self._locks.get(str(key))
        if lock is not None and not lock.locked():
            self._locks.pop(str(key), None)


class ActiveTurnCredentialLease:
    """Refresh credentials while DSH may be blocked inside long tool calls."""

    def __init__(
        self,
        refresher: CredentialRefresher,
        *,
        session_id: str,
        interval_seconds: float = 240.0,
    ) -> None:
        self._refresher = refresher
        self._session_id = str(session_id)
        self._interval = max(0.05, float(interval_seconds))
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(
                self._run(),
                name=f"dsh-credential-lease:{self._session_id}",
            )

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def refresh_now(self) -> None:
        try:
            await self._refresher.refresh_session_credentials(self._session_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            # A transient refresh failure must not cancel a browser operation;
            # the next lease tick and explicit approval refresh can recover it.
            logger.exception(
                "failed to refresh active DSH turn credentials",
                extra={"kernel_session_id": self._session_id},
            )

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            await self.refresh_now()


__all__ = ["ActiveTurnCredentialLease", "CredentialRefresher", "KeyedAsyncLock"]
