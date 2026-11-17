"""Instrument policy and persistence stages without recording tool arguments."""
import asyncio
from functools import wraps
import logging

from app.infrastructure.observability.spans import log_span


class ToolControlPlaneTimeout(RuntimeError):
    pass


def tool_stage(name, *, total=False, timeout_seconds=None):
    def decorate(method):
        @wraps(method)
        async def measured(*args, **kwargs):
            with log_span(f'tool.{name}', level=logging.INFO if total else logging.DEBUG):
                if timeout_seconds is None:
                    return await method(*args, **kwargs)
                try:
                    return await asyncio.wait_for(method(*args, **kwargs), timeout_seconds)
                except asyncio.TimeoutError as exc:
                    raise ToolControlPlaneTimeout(f'Tool control-plane stage {name} timed out; check its recorded outcome before retrying') from exc
        return measured
    return decorate
