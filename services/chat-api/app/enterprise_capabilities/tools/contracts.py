from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ToolExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profileVersion: str
    sessionId: str
    toolName: str
    actionId: str
    idempotencyKey: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ApprovalAskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profileVersion: str
    sessionId: str
    toolName: str
    actionId: str
    reason: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)
    timeoutSeconds: int = Field(default=300, ge=1, le=900)


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    grantScope: Literal["once", "session"] = "once"


class EnterpriseActionReceipt(BaseModel):
    schema_version: Literal["askai.enterprise-action-receipt.v1"] = "askai.enterprise-action-receipt.v1"
    action_id: str
    idempotency_key: str
    tenant_id: str
    user_id: str
    conversation_id: str
    kernel_session_id: str
    profile_version: str
    tool_name: str
    status: Literal["running", "succeeded", "failed", "cancelled", "timed_out"]
    result: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class EnterpriseApproval(BaseModel):
    schema_version: Literal["askai.enterprise-approval.v1"] = "askai.enterprise-approval.v1"
    action_id: str
    tenant_id: str
    user_id: str
    conversation_id: str
    kernel_session_id: str
    profile_version: str
    tool_name: str
    reason: str = ""
    message_id: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)
    scope_key: str = ""
    scope_label: str = ""
    grant_scope: Literal["once", "session"] = "once"
    status: Literal["pending", "approved", "rejected", "cancelled", "expired"] = "pending"
    decided_by: str = ""
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class EnterpriseSessionApprovalGrant(BaseModel):
    schema_version: Literal["askai.enterprise-session-approval-grant.v1"] = (
        "askai.enterprise-session-approval-grant.v1"
    )
    grant_id: str
    tenant_id: str
    user_id: str
    conversation_id: str
    profile_version: str
    tool_name: str
    scope_key: str
    scope_label: str = ""
    granted_by: str
    source_action_id: str
    status: Literal["active", "revoked"] = "active"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
