"""Process-local, zero-database live delivery for one DSH turn."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any


_END = object()


class LiveTurnStream:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[dict[str, Any] | object] = asyncio.Queue()
        self._accepting = True

    def publish(self, event: dict[str, Any]) -> None:
        if self._accepting:
            self._queue.put_nowait(event)

    def finish(self) -> None:
        if self._accepting:
            self._queue.put_nowait(_END)

    def detach(self) -> None:
        self._accepting = False
        while not self._queue.empty():
            self._queue.get_nowait()

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            item = await self._queue.get()
            if item is _END:
                return
            if isinstance(item, dict):
                yield item
