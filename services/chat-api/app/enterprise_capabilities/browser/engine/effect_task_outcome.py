"""Task-level disposition for one verified browser side effect."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal, Tuple


EffectTaskStatus = Literal["continue", "completed", "partial_success"]


@dataclass(frozen=True)
class EffectTaskOutcome:
    status: EffectTaskStatus
    reason: str = ""
    verified_requirements: Tuple[str, ...] = ()
    missing_requirements: Tuple[str, ...] = ()

    @property
    def terminal(self) -> bool:
        return self.status in {"completed", "partial_success"}

    @property
    def completed(self) -> bool:
        return self.status == "completed"

    @classmethod
    def continue_(cls) -> "EffectTaskOutcome":
        return cls(status="continue")

    @classmethod
    def complete(cls) -> "EffectTaskOutcome":
        return cls(status="completed")

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "verified_requirements": list(self.verified_requirements),
            "missing_requirements": list(self.missing_requirements),
        }


__all__ = ["EffectTaskOutcome", "EffectTaskStatus"]
