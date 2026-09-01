from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict

from pydantic import BaseModel, Field, field_validator


class CommentaryReason(str, Enum):
    INTENT = "intent"
    FINDING = "finding"
    TRANSITION = "transition"
    PIVOT = "pivot"
    PROGRESS = "progress"
    BLOCKER = "blocker"


class DecisionTurnVisibility(str, Enum):
    USER_VISIBLE = "user_visible"
    INTERNAL = "internal"


class ModelCommentary(BaseModel):
    text: str = Field(default="", max_length=600)
    reason: CommentaryReason = CommentaryReason.INTENT

    @field_validator("text", mode="before")
    @classmethod
    def _normalize_text(cls, value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()

    @field_validator("reason", mode="before")
    @classmethod
    def _normalize_reason(cls, value: Any) -> CommentaryReason:
        try:
            return CommentaryReason(str(value or "intent").strip().lower())
        except ValueError:
            return CommentaryReason.INTENT


class DecisionOutput(BaseModel):
    """Base for business schemas produced by an explicitly marked decision turn."""

    commentary: ModelCommentary | None = Field(
        default=None,
        description="Optional user-facing explanation of a material decision; presentation-only.",
        exclude=True,
    )

    @field_validator("commentary", mode="before")
    @classmethod
    def _tolerate_malformed_commentary(cls, value: Any) -> Any:
        # Presentation metadata must never invalidate an otherwise usable
        # business decision returned by a provider.
        return value if isinstance(value, (dict, ModelCommentary)) else None


_GENERIC_PATTERNS = (
    re.compile(r"^(正在|开始|即将)?(执行|处理|分析|规划|调用|生成|查询|搜索)(任务|请求|步骤|工具)?[。.!！]?$") ,
    re.compile(r"^(已|已经)?(完成|结束)(执行|处理|分析|规划|调用|生成|查询|搜索)?(任务|请求|步骤|工具)?[。.!！]?$") ,
    re.compile(r"^(working on|processing|analyzing|planning|executing|calling tools?)( the)?( task| request)?[.!]?$", re.I),
    re.compile(r"^(task|request|analysis|planning|execution)( is)? (complete|completed|done)[.!]?$", re.I),
)


def decision_commentary_dict(value: Any) -> Dict[str, Any] | None:
    if isinstance(value, ModelCommentary):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return dict(value)
    return None


def normalize_decision_commentary(value: Any, *, locale: str) -> Dict[str, str] | None:
    try:
        commentary = value if isinstance(value, ModelCommentary) else ModelCommentary.model_validate(value or {})
    except Exception:
        return None
    text = commentary.text.strip()
    if not text or len(text) < 8 or any(pattern.match(text) for pattern in _GENERIC_PATTERNS):
        return None
    requested = str(locale or "").strip().lower().replace("_", "-")
    normalized_locale = "en-US" if requested.startswith("en") else "zh-CN"
    return {"text": text, "reason": commentary.reason.value, "locale": normalized_locale, "source": "model"}
