from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field, model_validator


def _listify(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.replace("；", "\n").splitlines() if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


class PageVisualDirection(BaseModel):
    page_id: str = ""
    composition: str = "editorial_canvas"
    visual_story: str = ""
    visual_anchor: str = ""
    reading_flow: str = "left_to_right"
    region_plan: List[str] = Field(default_factory=list)
    surface_treatment: str = "flat_editorial"
    illustration_language: str = "gradient_vector_symbols"
    decoration_language: str = "restrained_geometry"
    typography_move: str = "large_takeaway_with_short_support"
    card_policy: str = "cards_only_when_the_content_is_truly_peer_based"
    accent_edge: str = "none"
    avoid_patterns: List[str] = Field(default_factory=list)
    copy_budget: Dict[str, int] = Field(default_factory=lambda: {
        "supporting_ideas": 5,
        "lines_per_idea": 2,
    })
    recommended_archetype: str = ""
    required_visual_elements: List["VisualElementRequirement"] = Field(default_factory=list)
    minimum_visual_blocks: int = 1

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        for key in ("region_plan", "avoid_patterns"):
            normalized[key] = _listify(normalized.get(key))
        budget = normalized.get("copy_budget")
        if not isinstance(budget, dict):
            normalized["copy_budget"] = {}
        return normalized


class VisualElementRequirement(BaseModel):
    element_id: str = "primary_anchor"
    kind: str = "hero_symbol"
    purpose: str = "Make the page's main conclusion visually obvious."
    content: str = ""
    placement: str = "dominant_region"
    minimum_scale: str = "large"
    required: bool = True


class DeckVisualPlan(BaseModel):
    deck_id: str = "presentation"
    design_thesis: str = "A coherent editorial presentation with varied whole-page compositions."
    design_language: List[str] = Field(default_factory=list)
    typography_language: str = "large editorial headlines with concise supporting copy"
    color_language: str = "one confident primary color, dark ink, white space, and restrained gradients"
    illustration_language: str = "editable vector symbols and simple visual metaphors"
    decoration_language: str = "sparse dot fields, soft waves, and purposeful directional marks"
    rhythm_rules: List[str] = Field(default_factory=list)
    page_directions: List[PageVisualDirection] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        for key in ("design_language", "rhythm_rules"):
            normalized[key] = _listify(normalized.get(key))
        if not isinstance(normalized.get("page_directions"), list):
            normalized["page_directions"] = []
        return normalized

    def for_page(self, page_id: str) -> PageVisualDirection | None:
        target = str(page_id or "").strip()
        for direction in self.page_directions:
            if str(direction.page_id or "").strip() == target:
                return direction
        return None

    def compact_payload(self) -> Dict[str, Any]:
        return {
            "design_thesis": self.design_thesis,
            "design_language": list(self.design_language or []),
            "typography_language": self.typography_language,
            "color_language": self.color_language,
            "illustration_language": self.illustration_language,
            "decoration_language": self.decoration_language,
            "rhythm_rules": list(self.rhythm_rules or []),
        }


PageVisualDirection.model_rebuild()


__all__ = ["DeckVisualPlan", "PageVisualDirection", "VisualElementRequirement"]
