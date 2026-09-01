"""Unified return type for every rule function.

Every rule (CRUD / form / scrape / nav) returns a CandidateSet. The
caller reads ``.action`` to decide whether to auto-execute, surface to
the LLM for disambiguation, or fall through to the planner entirely.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


AUTO_EXECUTE = "auto_execute"
LLM_PICK = "llm_pick"
FALLBACK = "fallback"
SKIP = "skip"


@dataclass
class CandidateSet:
    op: str
    tier: int
    items: List[Dict[str, Any]] = field(default_factory=list)
    reason: str = ""

    @property
    def action(self) -> str:
        n = len(self.items)
        if n == 0:
            return FALLBACK
        if n == 1:
            return AUTO_EXECUTE
        if n <= 8:
            return LLM_PICK
        return FALLBACK
