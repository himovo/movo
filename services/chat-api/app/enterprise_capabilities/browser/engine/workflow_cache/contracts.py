from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field


WorkflowStatus = Literal["candidate", "active", "degraded", "quarantined"]


class WorkflowIdentity(BaseModel):
    user_id: str
    main_id: str = "default"
    site_id: str
    operation_id: str
    capability_id: str
    signature_hash: str


class CachedParameterBinding(BaseModel):
    source: Literal["candidate", "request"]
    semantic_name: str = ""
    source_path: str = ""
    request_slot: int = -1
    projection: Literal["value", "plain_text", "rich_html", "files"] = "value"
    prefix: str = ""
    suffix: str = ""
    encoding: Literal["none", "url_query"] = "none"


class CachedRequestTemplate(BaseModel):
    """Static request fragments surrounding dynamic values; contains no values."""

    parts: List[str] = Field(default_factory=list)
    slot_count: int = 0


class CachedCompletionContract(BaseModel):
    capability_id: str = ""
    enabled: bool = True
    file_direction: Literal["upload", "download"] = "upload"


class CachedWorkflowStep(BaseModel):
    tool: str
    locator: Dict[str, Any] = Field(default_factory=dict)
    locator_bindings: Dict[str, CachedParameterBinding] = Field(default_factory=dict)
    args: Dict[str, Any] = Field(default_factory=dict)
    arg_bindings: Dict[str, CachedParameterBinding] = Field(default_factory=dict)
    source_url: str = ""
    source_url_shape: str = ""
    target_url_shape: str = ""
    expect_state_change: bool = False
    execution_kind: Literal["business_action", "runtime_precondition"] = "business_action"
    precondition_category: str = ""


class CachedFieldBinding(BaseModel):
    """A value-free memory of which business input belongs to a live field."""

    locator: Dict[str, Any] = Field(default_factory=dict)
    semantic_name: str
    source_path: str = ""
    action: Literal["fill", "select", "upload"]
    control_kind: str = ""


class CachedBrowserWorkflow(BaseModel):
    workflow_id: str
    display_name: str = ""
    admission_revision: int = 1
    identity: WorkflowIdentity
    status: WorkflowStatus = "candidate"
    version: int = 1
    steps: List[CachedWorkflowStep] = Field(default_factory=list)
    request_template: CachedRequestTemplate | None = None
    request_fingerprint: str = ""
    plan_hash: str = ""
    quality_score: int = 0
    supersedes_workflow_id: str = ""
    completion: CachedCompletionContract | None = None
    field_bindings: List[CachedFieldBinding] = Field(default_factory=list)
    dynamic_input_roles: List[str] = Field(default_factory=list)
    success_count: int = 1
    replay_success_count: int = 0
    failure_count: int = 0
    consecutive_failures: int = 0
    created_from_run_id: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    # Request-scoped replay instructions returned by semantic matching. They
    # are deliberately excluded from persistence; a later request must be
    # planned against its own goal and inputs.
    runtime_replay_step_count: int = Field(default=-1, exclude=True)
    runtime_missing_input_roles: List[str] = Field(default_factory=list, exclude=True)
    runtime_preconditions: List[Dict[str, Any]] = Field(default_factory=list, exclude=True)
