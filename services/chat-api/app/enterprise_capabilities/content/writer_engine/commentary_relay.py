from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable
from typing import Any, Generic, TypeVar, cast


T = TypeVar("T")
_MISSING = object()


class CommentaryRelay(Generic[T]):
    """Relay producer-owned commentary while a writer operation is running."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._result: T | object = _MISSING

    async def publish(self, payload: dict[str, Any]) -> None:
        await self._queue.put(dict(payload))

    async def stream(self, operation: Awaitable[T]) -> AsyncIterator[dict[str, Any]]:
        task = asyncio.ensure_future(operation)
        try:
            while not task.done() or not self._queue.empty():
                if not self._queue.empty():
                    yield self._queue.get_nowait()
                    continue
                commentary = asyncio.create_task(self._queue.get())
                try:
                    done, _ = await asyncio.wait(
                        {task, commentary}, return_when=asyncio.FIRST_COMPLETED
                    )
                    if commentary in done:
                        yield commentary.result()
                finally:
                    if not commentary.done():
                        commentary.cancel()
                    await asyncio.gather(commentary, return_exceptions=True)
            self._result = await task
        except BaseException:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise

    @property
    def result(self) -> T:
        if self._result is _MISSING:
            raise RuntimeError("writer operation has not completed")
        return cast(T, self._result)


__all__ = ["CommentaryRelay"]
