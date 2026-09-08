from __future__ import annotations

from typing import Any, Dict, List


_REFERENCES: Dict[str, Dict[str, Any]] = {
    "hero_focal": {
        "name": "hero_focal",
        "silhouette": "minimal copy on one side; one integrated semantic hero occupying 35-55% of the canvas",
        "visual_logic": "the hero explains the subject through a recognizable system, product, object, or metaphor",
        "depth": "use foreground/background scale, one contrast field, and restrained ambient detail",
        "avoid": ["empty rings", "random dot clusters", "generic title page decoration"],
    },
    "editorial_infographic": {
        "name": "editorial_infographic",
        "silhouette": "one dominant visual argument with concise annotations arranged around its geometry",
        "visual_logic": "convert the main claim into a relationship, transformation, tension, or cause-and-effect scene",
        "depth": "combine one substantial field with open typography and two supporting visual cues",
        "avoid": ["equal card wall", "floating labels", "web dashboard composition"],
    },
    "system_cutaway": {
        "name": "system_cutaway",
        "silhouette": "one integrated system body revealing layers, boundaries, and dependency direction",
        "visual_logic": "labels live inside or immediately beside the system parts they describe",
        "depth": "use nested planes, layer contrast, and a single foundation-to-outcome direction",
        "avoid": ["boxes connected by loose wires", "tiny architecture labels", "empty modules"],
    },
    "metric_narrative": {
        "name": "metric_narrative",
        "silhouette": "one decisive number or chart paired with a compact explanation of its meaning",
        "visual_logic": "comparison and implication are visible in the same reading path as the metric",
        "depth": "use scale contrast, one baseline or comparator, and a restrained evidence zone",
        "avoid": ["KPI card grid", "unexplained large number", "decorative progress bars"],
    },
    "journey_path": {
        "name": "journey_path",
        "silhouette": "one continuous path with three to five meaningfully different stages",
        "visual_logic": "position, scale, or elevation shows progression; labels attach to their stage",
        "depth": "highlight the destination and keep connectors behind content",
        "avoid": ["disconnected mini cards", "thin line as the only visual", "repeated identical nodes"],
    },
    "media_anchor": {
        "name": "media_anchor",
        "silhouette": "one substantial image or illustration balanced by a focused narrative field",
        "visual_logic": "the visual supplies evidence or context rather than acting as wallpaper",
        "depth": "use an intentional crop, one overlap or edge relationship, and a clean text-safe area",
        "avoid": ["tiny thumbnail", "image inside a browser-like card", "unrelated stock decoration"],
    },
}


_ARCHETYPE_REFERENCE = {
    "full_bleed_visual": ("hero_focal", "media_anchor"),
    "hero_statement": ("hero_focal", "editorial_infographic"),
    "accent_callout": ("hero_focal", "journey_path"),
    "dominant_panel": ("editorial_infographic", "hero_focal"),
    "asymmetric_split": ("editorial_infographic", "media_anchor"),
    "top_hero_bottom_detail": ("editorial_infographic", "metric_narrative"),
    "image_text_split": ("media_anchor", "editorial_infographic"),
    "architecture_blueprint": ("system_cutaway", "editorial_infographic"),
    "stacked_system": ("system_cutaway", "journey_path"),
    "layered_band": ("system_cutaway", "editorial_infographic"),
    "radial_feature_ring": ("system_cutaway", "editorial_infographic"),
    "timeline_spine": ("journey_path", "editorial_infographic"),
    "progressive_arrow_chain": ("journey_path", "editorial_infographic"),
    "alternating_zigzag": ("journey_path", "media_anchor"),
    "data_dashboard": ("metric_narrative", "editorial_infographic"),
    "big_number_row": ("metric_narrative", "editorial_infographic"),
    "stats_plus_narrative": ("metric_narrative", "editorial_infographic"),
}


def composition_references(archetype_id: str) -> List[Dict[str, Any]]:
    """Return compact quality references, never fixed coordinates or templates."""
    keys = _ARCHETYPE_REFERENCE.get(
        str(archetype_id or "").strip(),
        ("editorial_infographic", "hero_focal"),
    )
    return [dict(_REFERENCES[key]) for key in keys]


__all__ = ["composition_references"]
