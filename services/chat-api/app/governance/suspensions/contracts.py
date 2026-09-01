from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class SuspensionStatus(str, Enum):
    SUSPENDED = "suspended"
    READY = "ready"
    RESUMING = "resuming"
    RESUMED = "resumed"
    RESUME_FAILED = "resume_failed"
    DENIED = "denied"
    EXPIRED = "expired"


class SuspensionType(str, Enum):
    BROWSER_AUTH = "browser_auth"
    APPROVAL = "approval"
    USER_INPUT = "user_input"
    VERIFICATION = "verification"
    EXTERNAL_CALLBACK = "external_callback"


class SuspensionRecord(BaseModel):
    suspension_id: str
    run_id: str
    task_id: str
    node_id: str
    user_id: str
    subagent_id: str = ""
    suspension_type: str
    status: SuspensionStatus = SuspensionStatus.SUSPENDED
    reason: str = ""
    resume_policy: str = "manual"
    context: Dict[str, Any] = Field(default_factory=dict)
    ready_signal: Dict[str, Any] = Field(default_factory=dict)
    resume_token_hash: str = ""
    expires_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    ready_at: Optional[datetime] = None
    resumed_at: Optional[datetime] = None
