from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class CommandResult:
    name: str
    command: list[str]
    returncode: int
    duration_seconds: float
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        return self.returncode == 0

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "passed": self.passed}


@dataclass(frozen=True)
class PackageMetadata:
    name: str
    version: str
    dependencies: dict[str, str]
    dist: dict[str, Any]


@dataclass
class EvaluationReport:
    baseline_version: str
    candidate_version: str
    generated_at_utc: str
    package: dict[str, Any]
    dependency_delta: dict[str, Any] = field(default_factory=dict)
    public_api_delta: dict[str, Any] = field(default_factory=dict)
    capability_delta: dict[str, Any] = field(default_factory=dict)
    checks: list[dict[str, Any]] = field(default_factory=list)
    old_session_resume: dict[str, Any] = field(default_factory=dict)
    decision: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "askai.dsh-upgrade-evaluation.v1",
            **asdict(self),
        }
