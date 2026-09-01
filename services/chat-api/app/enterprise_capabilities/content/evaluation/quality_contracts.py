from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class QualityGates(BaseModel):
    goal_satisfied: bool = False
    granularity_fit: bool = False
    critical_fact_preservation: bool = False
    publish_ready: bool = False


class QualityScores(BaseModel):
    goal_satisfied_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    granularity_fit_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    critical_fact_preservation_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    publish_readiness_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_grounding_rate: float = Field(default=0.0, ge=0.0, le=1.0)


class QualityIssue(BaseModel):
    code: str
    severity: str = "minor"
    message: str = ""
    meta: Dict[str, Any] = Field(default_factory=dict)


class QualityReport(BaseModel):
    run_id: str = ""
    scores: QualityScores = Field(default_factory=QualityScores)
    gates: QualityGates = Field(default_factory=QualityGates)
    completion_gap_count: int = 0
    critical_fact_missing_count: int = 0
    rewrite_rounds: int = 0
    delta_gate_triggered: bool = False
    issues: List[QualityIssue] = Field(default_factory=list)

    def as_runtime_status(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "goal_satisfied_rate": self.scores.goal_satisfied_rate,
            "granularity_fit_rate": self.scores.granularity_fit_rate,
            "critical_fact_preservation_rate": self.scores.critical_fact_preservation_rate,
            "publish_readiness_rate": self.scores.publish_readiness_rate,
            "evidence_grounding_rate": self.scores.evidence_grounding_rate,
            "goal_satisfied": self.gates.goal_satisfied,
            "granularity_fit": self.gates.granularity_fit,
            "critical_fact_preservation": self.gates.critical_fact_preservation,
            "publish_ready": self.gates.publish_ready,
            "completion_gap_count": self.completion_gap_count,
            "critical_fact_missing_count": self.critical_fact_missing_count,
            "rewrite_rounds": self.rewrite_rounds,
            "delta_gate_triggered": self.delta_gate_triggered,
            "quality_issues": [i.model_dump() for i in self.issues],
        }
