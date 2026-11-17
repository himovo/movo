"""Keep script queue waits out of the HTTP control-plane worker budget."""
from functools import partial
from typing import Callable, TypeVar

import anyio

T = TypeVar('T')
# At most 100 admitted and 100 queued calls, matching the validated settings.
# A separate limiter keeps status/settings requests responsive under script load.
_SCRIPT_WORKERS = anyio.CapacityLimiter(200)


async def run_script_work(operation: Callable[[], T]) -> T:
    return await anyio.to_thread.run_sync(partial(operation), limiter=_SCRIPT_WORKERS)
