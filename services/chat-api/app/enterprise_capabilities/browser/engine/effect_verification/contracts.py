from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field


EffectStatus = Literal[
    "confirmed_success",
    "confirmed_failure",
    "pending",
    "unknown",
]


class EffectContract(BaseModel):
    action_name: str
    operation_family: str = "custom"
    entity: str = ""
    side_effect: Literal["none", "write", "destructive", "external"] = "write"
    is_commit: bool = False
    completes_goal: bool = False
    fingerprint: Dict[str, Any] = Field(default_factory=dict)
    expected_effects: List[str] = Field(default_factory=list)
    verification_hints: List[str] = Field(default_factory=list)
    intended_operation: str = ""
    intended_entity: str = ""
    target_operation: str = ""
    target_entity: str = ""
    semantic_confidence: float = 0.0
    source: Literal["local_rule", "model", "skill", "node_contract"] = "local_rule"
    business_action_id: str = ""
    action_attempt_id: str = ""
    business_target_id: str = ""
    observation_revision: str = ""

    def key(self) -> str:
        payload = {
            "action_name": self.action_name.strip().lower(),
            "operation_family": self.operation_family.strip().lower(),
            "entity": self.entity.strip().lower(),
            "intended_operation": self.intended_operation.strip().lower(),
            "intended_entity": self.intended_entity.strip().lower(),
            "target_operation": self.target_operation.strip().lower(),
            "target_entity": self.target_entity.strip().lower(),
            "fingerprint": self.fingerprint,
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


class EffectEvidence(BaseModel):
    evidence_id: str
    kind: str
    detail: str
    polarity: Literal["positive", "negative", "pending", "neutral"] = "neutral"
    weight: float = 0.0


class EffectReceipt(BaseModel):
    contract_key: str
    status: EffectStatus
    confidence: float = 0.0
    action_name: str
    operation_family: str = "custom"
    entity: str = ""
    side_effect: str = "write"
    completes_goal: bool = False
    evidence: List[EffectEvidence] = Field(default_factory=list)
    fingerprint: Dict[str, Any] = Field(default_factory=dict)
    verification_hints: List[str] = Field(default_factory=list)
    intended_operation: str = ""
    intended_entity: str = ""
    target_operation: str = ""
    target_entity: str = ""
    reason: str = ""
    business_action_id: str = ""
    action_attempt_id: str = ""
    business_target_id: str = ""
    observation_revision: str = ""

    @property
    def blocks_replay(self) -> bool:
        semantic_mismatch = any(item.kind == "semantic_mismatch" for item in self.evidence)
        return semantic_mismatch or self.status in {
            "confirmed_success", "confirmed_failure", "pending", "unknown",
        }
