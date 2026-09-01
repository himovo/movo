"""Ordered asynchronous persistence for ASKAI-owned side-band V3 rows."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from .repository import KernelEventRepository


@dataclass(frozen=True)
class ProjectionScope:
    tenant_id: str
    user_id: str
    conversation_id: str
    message_id: str
    kernel_session_id: str


@dataclass(frozen=True)
class _FlushBarrier:
    future: asyncio.Future[None]


_STOP = object()


class DurableProjectionWriter:
    def __init__(
        self,
        *,
        events: KernelEventRepository,
        scope: ProjectionScope,
        max_batch_size: int = 128,
        max_batch_delay_seconds: float = 0.2,
    ) -> None:
        self._events = events
        self._scope = scope
        self._max_batch_size = max(1, int(max_batch_size))
        self._max_delay = max(0.001, float(max_batch_delay_seconds))
        self._queue: asyncio.Queue[dict[str, Any] | _FlushBarrier | object] = asyncio.Queue()
        self._failure: BaseException | None = None
        self._task = asyncio.create_task(
            self._run(), name=f"dsh-side-projection-writer:{scope.message_id}"
        )

    def enqueue(self, row: dict[str, Any]) -> None:
        self._raise_if_failed()
        self._queue.put_nowait(dict(row))

    async def flush(self) -> None:
        self._raise_if_failed()
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._queue.put_nowait(_FlushBarrier(future))
        await future
        self._raise_if_failed()

    async def close(self) -> None:
        if self._task.done():
            await self._task
            return
        await self.flush()
        self._queue.put_nowait(_STOP)
        await self._task

    async def abort(self) -> None:
        if not self._task.done():
            self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)

    def _raise_if_failed(self) -> None:
        if self._failure is not None:
            raise RuntimeError("side-band event persistence failed") from self._failure
        if self._task.done() and not self._task.cancelled():
            error = self._task.exception()
            if error is not None:
                raise RuntimeError("side-band event persistence failed") from error

    async def _run(self) -> None:
        batch: list[dict[str, Any]] = []
        deadline: float | None = None
        try:
            while True:
                try:
                    if batch:
                        assert deadline is not None
                        timeout = max(0.0, deadline - asyncio.get_running_loop().time())
                        item = await asyncio.wait_for(self._queue.get(), timeout=timeout)
                    else:
                        item = await self._queue.get()
                except asyncio.TimeoutError:
                    await self._persist(batch)
                    batch, deadline = [], None
                    continue

                if isinstance(item, dict):
                    if not batch:
                        deadline = asyncio.get_running_loop().time() + self._max_delay
                    batch.append(item)
                    if len(batch) >= self._max_batch_size:
                        await self._persist(batch)
                        batch, deadline = [], None
                    continue
                if isinstance(item, _FlushBarrier):
                    await self._persist(batch)
                    batch, deadline = [], None
                    if not item.future.done():
                        item.future.set_result(None)
                    continue
                if item is _STOP:
                    await self._persist(batch)
                    return
                raise RuntimeError("unknown side-band writer command")
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            self._failure = exc
            self._fail_waiting_barriers(exc)
            raise

    async def _persist(self, batch: list[dict[str, Any]]) -> None:
        if not batch:
            return
        await self._events.persist_projections(batch, **self._scope.__dict__)

    def _fail_waiting_barriers(self, exc: BaseException) -> None:
        while not self._queue.empty():
            item = self._queue.get_nowait()
            if isinstance(item, _FlushBarrier) and not item.future.done():
                item.future.set_exception(exc)
