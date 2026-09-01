"""Engine-neutral inputs for one enterprise capability invocation.

These contracts intentionally contain no graph, scheduler, retry-loop, or
Agent lifecycle behavior.  DSH owns orchestration; an ASKAI capability only
receives a bounded task description and trusted turn inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from app.llm.types import Message


class CapabilityTask(BaseModel):
    node_id: str = Field(..., min_length=1)
    goal: str = Field(..., min_length=1)
    assigned_agent: str = Field(..., min_length=1)
    expected_artifacts: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    retry_policy: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    conditional_edges: list[dict[str, Any]] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


@dataclass
class CapabilityInputs:
    messages: list[Message]
    raw_messages: list[dict[str, Any]]
    intent: str
    output_spec: dict[str, Any]
    language: str
    cancel_event: Any = None
