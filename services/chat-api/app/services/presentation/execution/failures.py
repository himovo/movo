"""Bounded stage retries and actionable, credential-free presentation errors."""
from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

logger = logging.getLogger(__name__)
T = TypeVar("T")


class PresentationStepError(RuntimeError):
    def __init__(self, exc: Exception, *, stage: str, page_id: str = "", attempts: int = 1):
        status = getattr(exc, "status_code", None)
        response = getattr(exc, "response", None)
        status = status or getattr(response, "status_code", None)
        if status is None:
            # The shared image adapter preserves provider status in its error.
            match = re.search(r"\bhttp_(\d{3})\b", str(exc))
            status = int(match.group(1)) if match else None
        kind = type(exc).__name__
        if isinstance(exc, (TimeoutError, httpx.TimeoutException)) or "timeout" in kind.lower():
            category = "provider_timeout"
        elif isinstance(exc, httpx.TransportError) or kind == "APIConnectionError":
            category = "provider_connection"
        elif status == 402:
            category = "insufficient_balance"
        elif status in (401, 403):
            category = "provider_authentication"
        elif status == 429:
            category = "provider_rate_limit"
        elif isinstance(status, int) and status >= 500:
            category = "provider_unavailable"
        else:
            category = "generation_error"
        self.category = category
        self.stage = stage
        self.page_id = page_id
        self.attempts = attempts
        self.retryable = category in {
            "provider_timeout", "provider_connection", "provider_rate_limit", "provider_unavailable",
        }
        self.error_type = kind
        super().__init__(
            f"PPT {stage} failed: {category}; error_type={kind}; "
            f"page_id={page_id or 'deck'}; attempts={attempts}"
        )


async def run_generation_step(
    operation: Callable[[], Awaitable[T]], *, stage: str, page_id: str = "",
) -> T:
    for attempt in (1, 2):
        try:
            return await operation()
        except Exception as exc:
            failure = PresentationStepError(exc, stage=stage, page_id=page_id, attempts=attempt)
            logger.warning("presentation_step_failed %s", failure, exc_info=True)
            if not failure.retryable or attempt == 2:
                raise failure from exc
            await asyncio.sleep(0.5)
    raise AssertionError("Unreachable retry state")
