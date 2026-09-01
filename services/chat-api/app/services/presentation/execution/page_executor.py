from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar


TItem = TypeVar("TItem")
TPage = TypeVar("TPage")


class BoundedPageExecutor(Generic[TItem, TPage]):
    """Generate missing pages concurrently while preserving deck order."""

    def __init__(self, concurrency: int = 3) -> None:
        self._concurrency = max(1, min(6, int(concurrency)))

    async def run(
        self,
        *,
        items: list[TItem],
        item_id: Callable[[TItem], str],
        existing: dict[str, TPage],
        generate: Callable[[int, TItem], Awaitable[TPage]],
        checkpoint: Callable[[str, TPage], Awaitable[None]],
        check_cancelled: Callable[[], None],
    ) -> list[TPage]:
        results: list[TPage | None] = [None] * len(items)
        semaphore = asyncio.Semaphore(self._concurrency)

        async def produce(index: int, item: TItem) -> None:
            page_id = item_id(item)
            resumed = existing.get(page_id)
            if resumed is not None:
                results[index] = resumed
                return
            async with semaphore:
                check_cancelled()
                page = await generate(index, item)
                check_cancelled()
                await checkpoint(page_id, page)
                results[index] = page

        tasks = [asyncio.create_task(produce(index, item)) for index, item in enumerate(items)]
        try:
            await asyncio.gather(*tasks)
        except BaseException:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        return [page for page in results if page is not None]


__all__ = ["BoundedPageExecutor"]
