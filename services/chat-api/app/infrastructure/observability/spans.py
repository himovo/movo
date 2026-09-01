from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, Optional

from app.infrastructure.request_context import merge_request_context, reset_request_context


logger = logging.getLogger("app.observability.spans")


@dataclass
class SpanState:
    span_id: str
    name: str
    started_at: float
    attrs: Dict[str, Any] = field(default_factory=dict)
    parent_span_id: str = ""


_span_stack: ContextVar[list[SpanState]] = ContextVar("span_stack", default=[])


def current_span_snapshot() -> Dict[str, Any]:
    stack = list(_span_stack.get([]) or [])
    if not stack:
        return {}
    span = stack[-1]
    return {
        "span": span.name,
        "span_id": span.span_id,
        "parent_span_id": span.parent_span_id,
        "span_elapsed_ms": int((time.monotonic() - span.started_at) * 1000),
        **span.attrs,
    }


class log_span:
    def __init__(self, span: str, *, slow_ms: Optional[int] = None, level: int = logging.INFO, **attrs: Any) -> None:
        self.name = str(span)
        self.attrs = _clean(attrs)
        self.slow_ms = slow_ms
        self.level = level
        self.state: SpanState | None = None
        self.previous_context: Dict[str, Any] | None = None
        self.previous_stack: list[SpanState] = []

    def __enter__(self) -> "log_span":
        self._start()
        return self

    def __exit__(self, exc_type: Any, exc: BaseException | None, tb: Any) -> bool:
        self._finish(exc)
        return False

    async def __aenter__(self) -> "log_span":
        self._start()
        return self

    async def __aexit__(self, exc_type: Any, exc: BaseException | None, tb: Any) -> bool:
        self._finish(exc)
        return False

    def _start(self) -> None:
        stack = list(_span_stack.get([]) or [])
        parent = stack[-1].span_id if stack else ""
        self.state = SpanState(
            span_id=f"span_{uuid.uuid4().hex[:12]}",
            name=self.name,
            started_at=time.monotonic(),
            attrs=self.attrs,
            parent_span_id=parent,
        )
        self.previous_stack = stack
        _span_stack.set(stack + [self.state])
        self.previous_context = merge_request_context({"span_id": self.state.span_id, "parent_span_id": parent})
        logger.log(self.level, "span started", extra={"event": "span.started", "span": self.name, **self.attrs})

    def _finish(self, exc: BaseException | None) -> None:
        if self.state is None:
            return
        duration_ms = int((time.monotonic() - self.state.started_at) * 1000)
        extra = {"span": self.name, "duration_ms": duration_ms, **self.attrs}
        try:
            if exc is not None:
                logger.exception(
                    "span failed",
                    exc_info=(type(exc), exc, exc.__traceback__),
                    extra={
                        "event": "span.failed",
                        **extra,
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:500],
                    },
                )
            else:
                logger.log(self.level, "span finished", extra={"event": "span.finished", **extra})
                threshold = self.slow_ms if self.slow_ms is not None else _default_slow_ms()
                if threshold > 0 and duration_ms >= threshold:
                    logger.warning("span slow", extra={"event": "span.slow", **extra, "slow_threshold_ms": threshold})
        finally:
            _span_stack.set(self.previous_stack)
            reset_request_context(self.previous_context)


@contextlib.contextmanager
def request_watchdog(*, interval_seconds: float, total_started_at: float | None = None, **attrs: Any) -> Iterator[None]:
    if interval_seconds <= 0:
        yield
        return
    task: asyncio.Task | None = None
    stop_event = asyncio.Event()
    started_at = total_started_at if total_started_at is not None else time.monotonic()

    async def _run() -> None:
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            except asyncio.TimeoutError:
                span = current_span_snapshot()
                logger.info(
                    "request heartbeat",
                    extra={
                        "event": "request.heartbeat",
                        "total_elapsed_ms": int((time.monotonic() - started_at) * 1000),
                        "current_span": span.get("span", ""),
                        **span,
                        **_clean(attrs),
                    },
                )

    try:
        task = asyncio.create_task(_run())
        yield
    finally:
        stop_event.set()
        if task is not None:
            task.cancel()


def _default_slow_ms() -> int:
    try:
        from app.core.config import get_settings

        return int(get_settings().LOG_SLOW_SPAN_MS)
    except Exception:
        return 10000


def _clean(payload: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in dict(payload or {}).items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        out[str(key)] = value
    return out
