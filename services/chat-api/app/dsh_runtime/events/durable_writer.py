"""Ordered asynchronous batching for ASKAI's durable DSH event projection."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from app.dsh_runtime.bindings import KernelBindingRepository

from .repository import KernelEventRepository, KernelEventWrite


@dataclass(frozen=True)
class _FlushBarrier:
    future: asyncio.Future[None]


_STOP = object()


class DurableKernelEventWriter:
    """Persist ordered events in batches without backpressuring the live stream."""

    def __init__(
        self,
        *,
        events: KernelEventRepository,
        bindings: KernelBindingRepository,
        binding_id: str,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        message_id: str,
        max_batch_size: int = 256,
        max_batch_delay_seconds: float = 0.2,
    ) -> None:
        self._events = events
        self._bindings = bindings
        self._binding_id = binding_id
        self._tenant_id = tenant_id
        self._user_id = user_id
        self._conversation_id = conversation_id
        self._message_id = message_id
        self._max_batch_size = max(1, int(max_batch_size))
        self._max_delay = max(0.001, float(max_batch_delay_seconds))
        self._queue: asyncio.Queue[KernelEventWrite | _FlushBarrier | object] = asyncio.Queue()
        self._failure: BaseException | None = None
        self._task = asyncio.create_task(self._run(), name=f"dsh-event-writer:{message_id}")

    def enqueue(self, write: KernelEventWrite) -> None:
        self._raise_if_failed()
        self._queue.put_nowait(write)

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
            raise RuntimeError("DSH event batch persistence failed") from self._failure
        if self._task.done() and not self._task.cancelled():
            error = self._task.exception()
            if error is not None:
                raise RuntimeError("DSH event batch persistence failed") from error

    async def _run(self) -> None:
        batch: list[KernelEventWrite] = []
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
                    batch = []
                    deadline = None
                    continue

                if isinstance(item, KernelEventWrite):
                    if not batch:
                        deadline = asyncio.get_running_loop().time() + self._max_delay
                    batch.append(item)
                    if len(batch) >= self._max_batch_size:
                        await self._persist(batch)
                        batch = []
                        deadline = None
                    continue
                if isinstance(item, _FlushBarrier):
                    await self._persist(batch)
                    batch = []
                    deadline = None
                    if not item.future.done():
                        item.future.set_result(None)
                    continue
                if item is _STOP:
                    await self._persist(batch)
                    return
                raise RuntimeError("unknown DSH event writer command")
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            self._failure = exc
            self._fail_waiting_barriers(exc)
            raise

    async def _persist(self, batch: list[KernelEventWrite]) -> None:
        if not batch:
            return
        await self._events.persist_batch(
            batch,
            tenant_id=self._tenant_id,
            user_id=self._user_id,
            conversation_id=self._conversation_id,
            message_id=self._message_id,
        )
        await self._bindings.advance_cursor(
            self._binding_id,
            max(write.event.cursor for write in batch),
        )

    def _fail_waiting_barriers(self, exc: BaseException) -> None:
        while not self._queue.empty():
            item = self._queue.get_nowait()
            if isinstance(item, _FlushBarrier) and not item.future.done():
                item.future.set_exception(exc)
