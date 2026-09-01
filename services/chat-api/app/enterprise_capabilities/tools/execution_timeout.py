from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar


T = TypeVar("T")
ProgressSink = Callable[[dict[str, Any]], Awaitable[None]]


class ExecutionDeadlineExceeded(asyncio.TimeoutError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ExecutionTimeoutPolicy:
    total_seconds: float
    inactivity_seconds: float = 0.0

    @property
    def activity_aware(self) -> bool:
        return self.inactivity_seconds > 0


class ExecutionActivity:
    """Tracks real capability progress without manufacturing keepalives."""

    def __init__(self) -> None:
        self._event = asyncio.Event()
        self._last_activity = asyncio.get_running_loop().time()

    @property
    def last_activity(self) -> float:
        return self._last_activity

    def touch(self) -> None:
        self._last_activity = asyncio.get_running_loop().time()
        self._event.set()

    def progress_sink(self, sink: ProgressSink | None) -> ProgressSink:
        async def publish(event: dict[str, Any]) -> None:
            self.touch()
            if sink is not None:
                await sink(dict(event))

        return publish

    async def wait(self) -> None:
        await self._event.wait()
        self._event.clear()


async def execute_with_timeout(
    execution: Awaitable[T],
    *,
    policy: ExecutionTimeoutPolicy,
    activity: ExecutionActivity | None = None,
) -> T:
    """Run an execution with a hard cap and an optional activity deadline."""

    if not policy.activity_aware:
        try:
            return await asyncio.wait_for(execution, timeout=policy.total_seconds)
        except asyncio.TimeoutError as exc:
            raise ExecutionDeadlineExceeded("tool execution timed out") from exc

    tracker = activity or ExecutionActivity()
    loop = asyncio.get_running_loop()
    started_at = loop.time()
    task = asyncio.ensure_future(execution)
    try:
        while True:
            now = loop.time()
            total_remaining = policy.total_seconds - (now - started_at)
            inactivity_remaining = policy.inactivity_seconds - (now - tracker.last_activity)
            if total_remaining <= 0:
                raise ExecutionDeadlineExceeded("tool execution exceeded its maximum duration")
            if inactivity_remaining <= 0:
                raise ExecutionDeadlineExceeded("tool execution stopped reporting progress")

            activity_waiter = asyncio.create_task(tracker.wait())
            try:
                done, _ = await asyncio.wait(
                    {task, activity_waiter},
                    timeout=min(total_remaining, inactivity_remaining),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if task in done:
                    return task.result()
            finally:
                if not activity_waiter.done():
                    activity_waiter.cancel()
                await asyncio.gather(activity_waiter, return_exceptions=True)
    except BaseException:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        raise


__all__ = [
    "ExecutionActivity",
    "ExecutionDeadlineExceeded",
    "ExecutionTimeoutPolicy",
    "execute_with_timeout",
]
