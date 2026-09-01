from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


class ActionReceipt(BaseModel):
    action_id: str
    idempotency_key: str
    status: Literal["running", "succeeded", "failed", "failed_retryable", "abandoned"]
    result_ref: Dict[str, Any] = Field(default_factory=dict)
    evidence: Dict[str, Any] = Field(default_factory=dict)
    # Optional business identity for cross-run browser side effects.  Older
    # tool receipts remain valid because every field defaults to an empty
    # value; attempt idempotency continues to use ``idempotency_key``.
    business_key: str = ""
    actor_id: str = ""
    system_id: str = ""
    target_id: str = ""
    operation_id: str = ""
    purpose: str = ""
    replay_policy: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RunningReceiptPolicy(BaseModel):
    running_timeout_seconds: int = 300
    abandoned_retryable: bool = True
