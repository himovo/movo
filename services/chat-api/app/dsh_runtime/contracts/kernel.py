"""Command and identity models for AgentKernel Contract v1."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .versions import AGENT_KERNEL_CONTRACT_VERSION

NonEmptyId = str


class ContractModel(BaseModel):
    """Strict immutable base for values crossing the kernel boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SessionStatus(str, Enum):
    CREATING = "creating"
    IDLE = "idle"
    RUNNING = "running"
    WAITING = "waiting"
    CANCELLING = "cancelling"
    FAILED = "failed"
    DISPOSED = "disposed"


class SendMode(str, Enum):
    PROMPT = "prompt"
    FOLLOWUP = "followup"
    STEER = "steer"


class CreateRuntimeRequest(ContractModel):
    schema_version: Literal["askai.agent-kernel.v1"] = AGENT_KERNEL_CONTRACT_VERSION
    tenant_id: NonEmptyId = Field(min_length=1, max_length=256)
    profile_version: NonEmptyId = Field(min_length=1, max_length=256)
    isolation_key: NonEmptyId = Field(min_length=1, max_length=512)


class RuntimeHandle(ContractModel):
    schema_version: Literal["askai.agent-kernel.v1"] = AGENT_KERNEL_CONTRACT_VERSION
    runtime_id: NonEmptyId = Field(min_length=1, max_length=256)
    kernel: Literal["dsh"] = "dsh"
    kernel_version: NonEmptyId = Field(min_length=1, max_length=128)
    profile_version: NonEmptyId = Field(min_length=1, max_length=256)
    model_instance_id: NonEmptyId | None = Field(default=None, min_length=1, max_length=256)
    isolation_key: NonEmptyId = Field(min_length=1, max_length=512)


class SessionSpec(ContractModel):
    conversation_id: NonEmptyId = Field(min_length=1, max_length=256)
    tenant_id: NonEmptyId = Field(min_length=1, max_length=256)
    user_id: NonEmptyId = Field(min_length=1, max_length=256)
    profile_version: NonEmptyId = Field(min_length=1, max_length=256)
    preset_id: NonEmptyId = Field(default="askai-enterprise", min_length=1, max_length=128)
    execution_location: Literal["server", "desktop", "remote_sandbox"] = "server"
    workspace_id: NonEmptyId | None = Field(default=None, min_length=1, max_length=256)
    seed_runtime_id: NonEmptyId | None = Field(default=None, min_length=1, max_length=256)
    seed_session_id: NonEmptyId | None = Field(default=None, min_length=1, max_length=256)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_execution_boundary(self) -> "SessionSpec":
        if self.execution_location == "server" and self.workspace_id is not None:
            raise ValueError("server Session cannot reference a local Workspace")
        if self.preset_id == "code" and self.execution_location == "server":
            raise ValueError("code preset requires desktop or remote_sandbox execution")
        if self.execution_location == "desktop" and self.preset_id == "code" and self.workspace_id is None:
            raise ValueError("desktop code Session requires a DSH Workspace")
        if (self.seed_runtime_id is None) != (self.seed_session_id is None):
            raise ValueError("seed Runtime and Session identity must be supplied together")
        return self


class CreateSessionRequest(ContractModel):
    schema_version: Literal["askai.agent-kernel.v1"] = AGENT_KERNEL_CONTRACT_VERSION
    runtime_id: NonEmptyId = Field(min_length=1, max_length=256)
    session_spec: SessionSpec


class SessionHandle(ContractModel):
    schema_version: Literal["askai.agent-kernel.v1"] = AGENT_KERNEL_CONTRACT_VERSION
    runtime_id: NonEmptyId = Field(min_length=1, max_length=256)
    session_id: NonEmptyId = Field(min_length=1, max_length=256)
    conversation_id: NonEmptyId = Field(min_length=1, max_length=256)
    profile_version: NonEmptyId = Field(min_length=1, max_length=256)
    model_instance_id: NonEmptyId | None = Field(default=None, min_length=1, max_length=256)
    preset_id: NonEmptyId = Field(default="askai-enterprise", min_length=1, max_length=128)
    workspace_id: NonEmptyId | None = Field(default=None, min_length=1, max_length=256)
    status: SessionStatus


class ContentBlock(ContractModel):
    type: Literal["text", "image", "document", "artifact_ref"]
    data: dict[str, Any]


class TemporalContext(ContractModel):
    """ASKAI-owned trusted clock snapshot for one kernel turn."""

    captured_at_utc: datetime
    user_local_time: datetime
    user_timezone: str = Field(min_length=1, max_length=100)

    @field_validator("captured_at_utc", "user_local_time")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("temporal context timestamps must be timezone-aware")
        return value

    @field_validator("user_timezone")
    @classmethod
    def require_iana_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError("user_timezone must be a valid IANA timezone") from exc
        return value


class SendRequest(ContractModel):
    schema_version: Literal["askai.agent-kernel.v1"] = AGENT_KERNEL_CONTRACT_VERSION
    session_id: NonEmptyId = Field(min_length=1, max_length=256)
    request_id: NonEmptyId = Field(min_length=1, max_length=256)
    mode: SendMode = SendMode.PROMPT
    content: list[ContentBlock] = Field(min_length=1)
    temporal_context: TemporalContext | None = None
    turn_context: dict[str, Any] = Field(default_factory=dict)


class CancelSessionRequest(ContractModel):
    schema_version: Literal["askai.agent-kernel.v1"] = AGENT_KERNEL_CONTRACT_VERSION
    session_id: NonEmptyId = Field(min_length=1, max_length=256)
    cause: str = Field(min_length=1, max_length=1000)


class KernelError(ContractModel):
    schema_version: Literal["askai.agent-kernel.v1"] = AGENT_KERNEL_CONTRACT_VERSION
    code: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$", min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
