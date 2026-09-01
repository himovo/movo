from __future__ import annotations

from typing import Any, List

from pydantic import BaseModel, Field

from app.llm.decision_turn import DecisionOutput


class SearchCandidate(BaseModel):
    provider: str = ""
    query: str = ""
    title: str = ""
    url: str = ""
    snippet: str = ""
    score: float | None = None


class EvidenceItem(BaseModel):
    title: str = ""
    url: str = ""
    content: str = ""
    provider: str = ""
    query: str = ""
    confidence: float | None = None
    rationale: str = ""


class RejectedSource(BaseModel):
    title: str = ""
    url: str = ""
    reason: str = ""


class ResearchTurnDecision(DecisionOutput):
    accepted_evidence: List[EvidenceItem] = Field(default_factory=list)
    rejected_sources: List[RejectedSource] = Field(default_factory=list)
    next_queries: List[str] = Field(default_factory=list)
    done: bool = False
    rationale: str = ""


class ProgressiveResearchResult(BaseModel):
    ok: bool = True
    tool: str = "progressive_research"
    query: str = ""
    rounds: int = 0
    providers: List[str] = Field(default_factory=list)
    results: List[dict[str, Any]] = Field(default_factory=list)
    rejected_sources: List[dict[str, Any]] = Field(default_factory=list)
    search_trace: List[dict[str, Any]] = Field(default_factory=list)
    summary: str = ""
    error: str = ""
    evidence_sufficient: bool = False
    budget_exhausted: bool = False
    stop_reason: str = ""
