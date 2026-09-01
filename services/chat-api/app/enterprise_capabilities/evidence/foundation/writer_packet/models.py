from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class SourceCoverage(BaseModel):
    input_records: int = 0
    included_materials: int = 0
    deduplicated_materials: int = 0
    filtered_records: int = 0
    unsupported_records: int = 0


class WriterEvidenceCoverage(BaseModel):
    scope: str = "writer_inputs_after_runtime_normalization"
    complete: bool = True
    truncated: bool = False
    source_types: Dict[str, SourceCoverage] = Field(default_factory=dict)
    unsupported_records: List[Dict[str, Any]] = Field(default_factory=list)
    filtered_structured_facts: int = 0
    suppressed_duplicate_representations: int = 0
    notes: List[str] = Field(default_factory=list)


class WriterEvidencePacket(BaseModel):
    schema_version: str = "writer-evidence-packet/v1-shadow"
    subject: Dict[str, Any] = Field(default_factory=dict)
    confirmed_facts: List[str] = Field(default_factory=list)
    business_datasets: List[Dict[str, Any]] = Field(default_factory=list)
    computed_metrics: List[Dict[str, Any]] = Field(default_factory=list)
    source_excerpts: List[Dict[str, Any]] = Field(default_factory=list)
    citations: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_items: List[Dict[str, Any]] = Field(default_factory=list)
    multimodal_facts: List[Dict[str, Any]] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)
    execution_failures: List[Dict[str, Any]] = Field(default_factory=list)
    coverage: WriterEvidenceCoverage = Field(default_factory=WriterEvidenceCoverage)
