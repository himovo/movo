from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Generic, Sequence, TypeVar

from app.enterprise_capabilities.content.evaluation.outcomes import EvaluationStageOutcome


T = TypeVar("T")


@dataclass(frozen=True)
class EvaluationRetryPolicy:
    """Bounded retries for provider-dependent quality evaluation stages."""

    standards_timeouts: tuple[float, ...] = (90.0, 60.0)
    issues_timeouts: tuple[float, ...] = (120.0, 90.0)
    total_timeout_seconds: float = 270.0


@dataclass(frozen=True)
class StageRunResult(Generic[T]):
    outcome: EvaluationStageOutcome[T]
    attempts: int


def evaluation_deadline(policy: EvaluationRetryPolicy) -> float:
    return time.monotonic() + max(1.0, float(policy.total_timeout_seconds))


def is_retryable_stage_error(error_type: str) -> bool:
    normalized = str(error_type or "").strip().lower()
    return any(
        token in normalized
        for token in ("timeout", "connection", "network", "protocol", "ratelimit", "rate_limit")
    )


async def run_evaluation_stage(
    factory: Callable[[], Awaitable[EvaluationStageOutcome[T]]],
    *,
    attempt_timeouts: Sequence[float],
    deadline: float,
) -> StageRunResult[T]:
    last = EvaluationStageOutcome.failed(TimeoutError("evaluation time budget exhausted"))
    attempts = 0

    for configured_timeout in attempt_timeouts:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        attempts += 1
        try:
            last = await asyncio.wait_for(
                factory(),
                timeout=max(0.1, min(float(configured_timeout), remaining)),
            )
        except Exception as exc:
            last = EvaluationStageOutcome.failed(exc)
        if last.completed or not is_retryable_stage_error(last.error_type):
            break

    return StageRunResult(outcome=last, attempts=attempts)
