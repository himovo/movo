from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field, field_validator
from app.llm.decision_turn import DecisionOutput


def _coerce_str_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        token = value.strip()
        return [token] if token else []
    if isinstance(value, dict):
        values = value.values()
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = [value]
    return [str(item).strip() for item in values if str(item or "").strip()]


def _coerce_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        token = value.strip()
        return {"instructions": token} if token else {}
    return {"value": value}


class SectionFactSpec(BaseModel):
    fact_id: str = ""
    fact_type: str = ""
    summary: str = ""
    source_kind: str = ""
    source_ref: str = ""
    raw_evidence: str = ""


class PlanSectionSpec(BaseModel):
    section_id: str = ""
    title: str = ""
    role: str = ""
    purpose: str = ""
    key_points: List[str] = Field(default_factory=list)
    evidence_focus: List[str] = Field(default_factory=list)
    must_cover_facts: List[SectionFactSpec] = Field(default_factory=list)
    allowed_claim_types: List[str] = Field(default_factory=list)
    disallowed_claim_types: List[str] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)
    visual_hint: str = "none"
    target_words: int = 0

    @field_validator(
        "key_points",
        "evidence_focus",
        "allowed_claim_types",
        "disallowed_claim_types",
        "open_questions",
        mode="before",
    )
    @classmethod
    def _coerce_string_lists(cls, value: Any) -> List[str]:
        return _coerce_str_list(value)


class VisualSlotSpec(BaseModel):
    slot_id: str = ""
    role: str = ""
    anchor_section_id: str = ""
    description: str = ""


class ContentPlanSpec(DecisionOutput):
    plan_id: str = ""
    thesis: str = ""
    central_answer: str = ""
    execution_mode: str = ""
    sections: List[PlanSectionSpec] = Field(default_factory=list)
    visual_slots: List[VisualSlotSpec] = Field(default_factory=list)
    handoff_contract: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("handoff_contract", "metadata", mode="before")
    @classmethod
    def _coerce_mapping_fields(cls, value: Any) -> Dict[str, Any]:
        return _coerce_dict(value)
