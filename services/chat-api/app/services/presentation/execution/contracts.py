from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


PresentationJobStatus = Literal[
    "pending",
    "running",
    "interrupted",
    "succeeded",
    "failed",
    "cancelled",
]


class PresentationJobSnapshot(BaseModel):
    job_id: str
    business_key: str
    continuation_token: str
    request_fingerprint: str
    tenant_id: str
    user_id: str
    conversation_id: str
    message_id: str
    generation_mode: str = "llm"
    owner_action_id: str = ""
    status: PresentationJobStatus = "pending"
    stage: str = "pending"
    story_plan: dict[str, Any] = Field(default_factory=dict)
    planning: dict[str, Any] = Field(default_factory=dict)
    pages: dict[str, dict[str, Any]] = Field(default_factory=dict)
    final_result: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    lease_expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @property
    def terminal(self) -> bool:
        return self.status in {"succeeded", "cancelled"}


class PresentationJobClaim(BaseModel):
    snapshot: PresentationJobSnapshot
    acquired: bool


__all__ = [
    "PresentationJobClaim",
    "PresentationJobSnapshot",
    "PresentationJobStatus",
    "utc_now",
]
