"""Stable ASKAI event envelope projected from DSH SessionEvent values."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .versions import KERNEL_EVENT_VERSION


class EventContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class KernelEventSource(EventContractModel):
    kernel: Literal["dsh"] = "dsh"
    kernel_version: str = Field(min_length=1, max_length=128)
    native_event_type: str | None = Field(default=None, max_length=256)


class KernelEventEnvelope(EventContractModel):
    schema_version: Literal["askai.kernel-event.v1"] = KERNEL_EVENT_VERSION
    event_id: str = Field(min_length=1, max_length=256)
    runtime_id: str = Field(min_length=1, max_length=256)
    session_id: str = Field(min_length=1, max_length=256)
    parent_session_id: str | None = Field(default=None, min_length=1, max_length=256)
    profile_version: str = Field(min_length=1, max_length=256)
    cursor: int = Field(ge=0)
    type: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$", min_length=1, max_length=256)
    occurred_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)
    source: KernelEventSource

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        return value
