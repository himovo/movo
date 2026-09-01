from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field, model_validator


class NormalizedBBox(BaseModel):
    x: float = 0.0
    y: float = 0.0
    w: float = 0.1
    h: float = 0.1

    @model_validator(mode="after")
    def _clamp(self) -> "NormalizedBBox":
        self.x = max(0.0, min(0.98, float(self.x or 0.0)))
        self.y = max(0.0, min(0.98, float(self.y or 0.0)))
        self.w = max(0.001, min(1.0 - self.x, float(self.w or 0.001)))
        self.h = max(0.001, min(1.0 - self.y, float(self.h or 0.001)))
        return self


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
    planned_texts: List[PlannedText] = Field(default_factory=list)
    planned_data: List[Dict[str, Any]] = Field(default_factory=list)
    full_slide_prompt: str = ""
    visual_must_haves: List[str] = Field(default_factory=list)
    reconstruction_rules: List[str] = Field(default_factory=list)


ElementType = Literal[
    "background",
    "illustration",
    "panel",
    "shape",
    "circle",
    "line",
    "icon",
    "diagram",
    "chart",
    "text",
    "table",
    "decorative",
]
RenderStrategy = Literal["freeform_block", "image_asset", "svg_shape", "chart_block", "ignore"]


class VisualElement(BaseModel):
    id: str = ""
    type: ElementType = "shape"
    semantic_role: str = ""
    bbox: NormalizedBBox = Field(default_factory=NormalizedBBox)
    z_index: int = 1
    render_strategy: RenderStrategy = "freeform_block"
    style: Dict[str, Any] = Field(default_factory=dict)
    content_hint: str = ""
    text: str = ""
    role: str = ""
    align: str = ""
    font: Dict[str, Any] = Field(default_factory=dict)
    asset_prompt: str = ""
    text_ref_id: str = ""
    confidence: float = 0.7
    group_id: str = ""
    parent_group_id: str = ""
    structural_role: str = ""
    context_type: str = ""
    visual_description: str = ""
    geometry_hint: str = ""
    nearby_text: str = ""
    relation_tags: List[str] = Field(default_factory=list)
    preserve_mode: str = ""
    editable_priority: str = ""


class VisualTextElement(BaseModel):
    id: str = ""
    bbox: NormalizedBBox = Field(default_factory=NormalizedBBox)
    z_index: int = 1
    text: str = ""
    role: str = "body"
    align: str = "left"
    font: Dict[str, Any] = Field(default_factory=dict)
    text_ref_id: str = ""
    confidence: float = 0.7
    group_id: str = ""
    structural_role: str = ""
    nearby_visual_id: str = ""
    source: str = ""


class VisualGroup(BaseModel):
    id: str = ""
    group_type: str = ""
    semantic_role: str = ""
    bbox: NormalizedBBox = Field(default_factory=NormalizedBBox)
    child_ids: List[str] = Field(default_factory=list)
    parent_group_id: str = ""
    layout_pattern: str = ""
    importance: str = ""
    preserve_mode: str = ""
    notes: str = ""


class VisualRelationship(BaseModel):
    source_id: str = ""
    target_id: str = ""
    relation_type: str = ""
    description: str = ""
    importance: str = ""


class VisualRegion(BaseModel):
    id: str = ""
    region_type: str = ""
    semantic_role: str = ""
    bbox: NormalizedBBox = Field(default_factory=NormalizedBBox)
    complexity: str = ""
    analysis_strategy: str = ""
    expected_element_types: List[str] = Field(default_factory=list)
    related_group_ids: List[str] = Field(default_factory=list)
    notes: str = ""


class VisualRegionAnalysis(BaseModel):
    page_id: str = ""
    canvas: Dict[str, Any] = Field(default_factory=lambda: {"w": 1600, "h": 900, "aspect": "16:9"})
    style: Dict[str, Any] = Field(default_factory=dict)
    layout: Dict[str, Any] = Field(default_factory=dict)
    regions: List[VisualRegion] = Field(default_factory=list)
    reconstruction_notes: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)


class VisualSemanticAnalysis(BaseModel):
    page_id: str = ""
    canvas: Dict[str, Any] = Field(default_factory=lambda: {"w": 1600, "h": 900, "aspect": "16:9"})
    style: Dict[str, Any] = Field(default_factory=dict)
    layout: Dict[str, Any] = Field(default_factory=dict)
    regions: List[VisualRegion] = Field(default_factory=list)
    elements: List[VisualElement] = Field(default_factory=list)
    text_elements: List[VisualTextElement] = Field(default_factory=list)
    groups: List[VisualGroup] = Field(default_factory=list)
    relationships: List[VisualRelationship] = Field(default_factory=list)
    image_assets: List[Dict[str, Any]] = Field(default_factory=list)
    reconstruction_notes: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)


class ImageNativePageArtifact(BaseModel):
    page_id: str
    image_url: str = ""
    image_object_path: str = ""
    image_prompt: str = ""
    analysis: Dict[str, Any] = Field(default_factory=dict)
