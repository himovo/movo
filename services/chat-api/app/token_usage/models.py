from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class TokenUsageRecord(BaseModel):
    request_id: str
    user_request_id: str = ""
    main_id: str = "default"
    user_id: str = ""
    session_id: str = ""
    trace_id: str = ""
    stage: str = ""
    intent: str = ""
    node_id: str = ""
    status: str = "completed"
    model_name: str = ""
    model_id: str = ""
    prompt: str = ""
    request_title_zh: str = ""
    request_title_en: str = ""
    request_payload: Dict[str, Any] = Field(default_factory=dict)
    response_payload: Dict[str, Any] = Field(default_factory=dict)
    start_time: int = 0
    end_time: int = 0
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    push_status: str = "pending"
    push_error: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TokenUsagePushResult(BaseModel):
    enabled: bool = False
    pushed: bool = False
    error: str = ""
