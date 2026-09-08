from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PlannedText(BaseModel):
    id: str = ""
    role: str = "body"
    text: str = ""
    priority: int = 5


class ImageNativePagePlan(BaseModel):
    page_id: str = ""
    page_index: int = 0
    page_type: str = "content"
    page_goal: str = ""
    key_takeaway: str = ""
    visual_intent: str = ""
    composition_intent: str = ""
    planned_texts: list[PlannedText] = Field(default_factory=list)
    planned_data: list[dict[str, Any]] = Field(default_factory=list)
    full_slide_prompt: str = ""
    visual_must_haves: list[str] = Field(default_factory=list)
    delivery_notes: list[str] = Field(default_factory=list)


__all__ = [
    "ImageNativePagePlan",
    "PlannedText",
]
