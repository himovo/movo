from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .timeouts import MAX_CAPABILITY_EXECUTION_MS


class CapabilityDefinition(BaseModel):
    """Immutable enterprise capability contract compiled into a DSH Tool."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    capability_ref: str = Field(pattern=r"^[a-z][a-z0-9_.-]+@v[1-9][0-9]*$")
    tool_name: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_]{0,127}$")
    version: str = Field(min_length=1, max_length=128)
    domain: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    display_name: str = Field(min_length=1, max_length=256)
    description: str = Field(min_length=1, max_length=4000)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] = Field(default_factory=dict)
    output_validation: Literal["none", "strict"] = "strict"
    risk_level: Literal["read", "write", "dangerous"] = "read"
    approval_required: bool = False
    approval_argument: str = ""
    approval_values: tuple[str, ...] = ()
    required_scopes: tuple[str, ...] = ("capabilities:read",)
    timeout_ms: int = Field(default=30_000, ge=100, le=MAX_CAPABILITY_EXECUTION_MS)
    timeout_mode: Literal["fixed", "activity"] = "fixed"
    inactivity_timeout_ms: int = Field(default=0, ge=0, le=MAX_CAPABILITY_EXECUTION_MS)
    cancellable: bool = True
    idempotent: bool = True
    delivery_mode: Literal["model_synthesized", "authoritative_markdown"] = "model_synthesized"
    consumes_execution_evidence: bool = False


class CapabilityExecutionContext(BaseModel):
    """Trusted identity and turn scope. None of these values come from the model."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    tenant_id: str
    user_id: str
    conversation_id: str
    kernel_session_id: str
    profile_version: str
    action_id: str
    message_id: str = ""
    model_instance_id: str = ""
    turn_context: dict[str, Any] = Field(default_factory=dict)
    cancel_event: Any = Field(default=None, exclude=True, repr=False)
    progress_sink: Callable[[dict[str, Any]], Awaitable[None]] | None = Field(
        default=None, exclude=True, repr=False
    )

    async def publish_progress(self, event: dict[str, Any]) -> None:
        if self.progress_sink is not None:
            await self.progress_sink(dict(event))
