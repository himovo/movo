from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field, model_validator


ScheduleKind = Literal["once", "daily", "weekly"]
SessionMode = Literal["fixed", "new_per_run"]


class ScheduledJobCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=20000)
    schedule_kind: ScheduleKind = "daily"
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=80)
    run_at: datetime
    weekdays: list[int] = Field(default_factory=list)
    session_mode: SessionMode = "fixed"
    session_id: Optional[str] = None
    session_title_template: str = Field(default="{name} · {date}", max_length=160)
    enabled: bool = True
    output_spec: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_target(self) -> "ScheduledJobCreate":
        if self.session_mode == "fixed" and not str(self.session_id or "").strip():
            raise ValueError("固定会话模式必须选择目标会话")
        if self.schedule_kind == "weekly":
            normalized = sorted({int(day) for day in self.weekdays})
            if not normalized or any(day < 0 or day > 6 for day in normalized):
                raise ValueError("每周任务必须选择有效星期")
            self.weekdays = normalized
        return self


class ScheduledJobUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    prompt: Optional[str] = Field(default=None, min_length=1, max_length=20000)
    schedule_kind: Optional[ScheduleKind] = None
    timezone: Optional[str] = Field(default=None, min_length=1, max_length=80)
    run_at: Optional[datetime] = None
    weekdays: Optional[list[int]] = None
    session_mode: Optional[SessionMode] = None
    session_id: Optional[str] = None
    session_title_template: Optional[str] = Field(default=None, max_length=160)
    enabled: Optional[bool] = None
    output_spec: Optional[Dict[str, Any]] = None


class ScheduledJobRunNow(BaseModel):
    pass
