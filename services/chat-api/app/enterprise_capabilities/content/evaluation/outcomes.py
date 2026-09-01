from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, List, TypeVar


T = TypeVar("T")


@dataclass
class EvaluationStageOutcome(Generic[T]):
    """Distinguish a valid empty result from an unavailable LLM result."""

    items: List[T] = field(default_factory=list)
    commentary: Any = None
    status: str = "completed"
    error_type: str = ""
    error: str = ""

    @property
    def completed(self) -> bool:
        return self.status == "completed"

    @classmethod
    def failed(cls, exc: BaseException) -> "EvaluationStageOutcome[T]":
        return cls(
            status="failed",
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )
