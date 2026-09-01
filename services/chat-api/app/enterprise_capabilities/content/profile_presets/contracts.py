from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class ComposeProfile(BaseModel):
    intent_statement: str = ""
    deliverable_signature: str = ""
    audience_model: str = ""
    style_axes: Dict[str, Any] = Field(default_factory=dict)
    hard_constraints: Dict[str, Any] = Field(default_factory=dict)
    raw_request: str = ""
    confidence: float = 0.0


class VisualContract(BaseModel):
    visual_goals: List[str] = Field(default_factory=list)
    visual_types: List[str] = Field(default_factory=list)
    density: Dict[str, Any] = Field(default_factory=dict)
    placement_policy: Dict[str, Any] = Field(default_factory=dict)
    style_constraints: Dict[str, Any] = Field(default_factory=dict)
    fallback_policy: Dict[str, Any] = Field(default_factory=dict)


class ProfilePreset(BaseModel):
    # Default to empty so LLM-synthesised presets aren't rejected at
    # validation time when the model omits this field — _normalize() in
    # DynamicPresetSynthesizer already fills it with a fallback id.
    preset_id: str = ""
    source: str = "builtin"
    # Minimal high-impact spec fields (contract-first)
    identity: str = ""

    # LLMs occasionally synthesise `identity` as a dict (e.g.
    # {"role": "...", "audience": "..."}) instead of a flat string.
    # Coerce gracefully so a single field-level mistake doesn't abort
    # the whole synthesis and force a fallback preset.
    @field_validator("identity", mode="before")
    @classmethod
    def _coerce_identity(cls, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            parts: List[str] = []
            for key in ("role", "title", "persona", "audience", "tone", "style", "context"):
                fragment = value.get(key)
                if fragment:
                    parts.append(f"{key}: {str(fragment).strip()}")
            for key, fragment in value.items():
                if key in {"role", "title", "persona", "audience", "tone", "style", "context"}:
                    continue
                if fragment:
                    parts.append(f"{str(key).strip()}: {str(fragment).strip()}")
            return " | ".join(parts)
        if isinstance(value, list):
            return " | ".join(str(item).strip() for item in value if item)
        return str(value).strip()
    style_reference: Dict[str, Any] = Field(default_factory=dict)
    must_include: List[str] = Field(default_factory=list)
    anti_patterns: Dict[str, Any] = Field(default_factory=dict)
    formatting_rules: Dict[str, Any] = Field(default_factory=dict)

    # LLMs occasionally synthesise list-shaped formatting_rules
    # (["use markdown H2", "avoid filler", ...]) instead of the contracted
    # dict shape. Coerce to {"rules": [...]} rather than failing the entire
    # synthesis and degrading to a generic fallback preset (which then loses
    # all the user-specific signals the LLM was about to inject).
    @field_validator("formatting_rules", "anti_patterns", "compose_policy",
                     "structure_contract", "evidence_policy", "quality_gates",
                     "output_contract", "style_reference", "metadata", mode="before")
    @classmethod
    def _coerce_dict_field(cls, value: Any) -> Any:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, list):
            return {"rules": [str(item).strip() for item in value if str(item).strip()]}
        return {"value": str(value)}
    # Legacy-compatible fields
    compose_policy: Dict[str, Any] = Field(default_factory=dict)
    structure_contract: Dict[str, Any] = Field(default_factory=dict)
    evidence_policy: Dict[str, Any] = Field(default_factory=dict)
    visual_contract: VisualContract = Field(default_factory=VisualContract)
    quality_gates: Dict[str, Any] = Field(default_factory=dict)
    forbidden_patterns: List[str] = Field(default_factory=list)
    output_contract: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PresetCandidate(BaseModel):
    preset: ProfilePreset
    fit_score: float = 0.0
    constraint_score: float = 0.0
    risk_penalty: float = 0.0
    total_score: float = 0.0
    hard_conflicts: List[str] = Field(default_factory=list)
    soft_conflicts: List[str] = Field(default_factory=list)
    reason: str = ""


class PresetResolution(BaseModel):
    selected_preset: Optional[ProfilePreset] = None
    candidates: List[PresetCandidate] = Field(default_factory=list)
    need_dynamic: bool = False
    decision_reason: str = ""
    used_dynamic: bool = False
    trace: Dict[str, Any] = Field(default_factory=dict)
