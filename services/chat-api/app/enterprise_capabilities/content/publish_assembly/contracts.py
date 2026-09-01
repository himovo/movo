from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class GeneratedVisualAssetSpec(BaseModel):
    slot_id: str = ""
    role: str = ""
    anchor_section_id: str = ""
    alt_text: str = ""
    image_url: str = ""
    status: str = "missing"
    reason: str = ""


class PublishAssemblySpec(BaseModel):
    body_markdown: str = ""
    final_markdown: str = ""
    generated_assets: List[GeneratedVisualAssetSpec] = Field(default_factory=list)
    missing_slot_ids: List[str] = Field(default_factory=list)
    missing_slot_reasons: List[str] = Field(default_factory=list)


class BrowserPublishMediaSpec(BaseModel):
    source_url: str
    kind: str = "image"
    order: int = 0
    alt_text: str = ""
    publishable: bool = True
    anchor_after_text: str = ""
    anchor_before_text: str = ""
    anchor_plain_offset: int = 0


class BrowserPublishPayload(BaseModel):
    schema_version: str = "1.0"
    title: str = ""
    body_markdown: str = ""
    body_plain_text: str = ""
    body_html: str = ""
    media: List[BrowserPublishMediaSpec] = Field(default_factory=list)
