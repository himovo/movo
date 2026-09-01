from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class ExecutionModeDecision(BaseModel):
    mode: str = "direct_compose"
    score: int = 0
    reasons: List[str] = Field(default_factory=list)
