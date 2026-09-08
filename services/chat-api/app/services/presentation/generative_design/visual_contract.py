from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.services.presentation.contracts import PageBrief

from .contracts import PageVisualDirection, VisualElementRequirement


_DATA_ARCHETYPES = {"data_dashboard", "big_number_row", "stats_plus_narrative", "structured_matrix"}
_SYSTEM_ARCHETYPES = {"architecture_blueprint", "stacked_system", "layered_band", "radial_feature_ring"}
_JOURNEY_ARCHETYPES = {"timeline_spine", "progressive_arrow_chain", "alternating_zigzag"}


def _requirements(page: PageBrief) -> List[VisualElementRequirement]:
    page_type = str(page.page_type or "content").strip().lower()
    archetype = str(page.layout_archetype_id or "dominant_panel").strip()
    takeaway = str(page.key_takeaway or page.visual_intent or page.page_goal or "").strip()
    if page_type == "cover":
        return [
            VisualElementRequirement(
                element_id="semantic_hero",
                kind="hero_visual",
                purpose="Represent the actual subject with an integrated visual, not abstract decoration.",
                content=takeaway,
                placement="dominant 35-55% canvas region",
                minimum_scale="hero",
            ),
            VisualElementRequirement(
                element_id="title_relationship",
                kind="composition_relationship",
                purpose="Bind title, hero, and metadata into one intentional reading path.",
                content=takeaway,
                placement="between title field and hero",
                minimum_scale="medium",
            ),
            VisualElementRequirement(
                element_id="spatial_atmosphere",
                kind="background_field",
                purpose="Create depth and a designed text-safe region without random dots or empty rings.",
                placement="full canvas",
                minimum_scale="large",
            ),
        ]
    if page_type == "thank_you":
        return [
            VisualElementRequirement(
                element_id="resolved_thesis",
                kind="hero_statement",
                purpose="Resolve the deck's opening idea instead of showing a generic thank-you message.",
                content=takeaway,
                placement="primary field",
                minimum_scale="hero",
            ),
            VisualElementRequirement(
                element_id="next_action",
                kind="action_path",
                purpose="Give the audience one concrete next step or durable takeaway.",
                placement="supporting field",
                minimum_scale="medium",
            ),
        ]
    if archetype in _SYSTEM_ARCHETYPES:
        return [
            VisualElementRequirement(element_id="system_body", kind="integrated_system", purpose="Show the system as one coherent body.", content=takeaway, placement="dominant region", minimum_scale="hero"),
            VisualElementRequirement(element_id="dependency_logic", kind="relationship", purpose="Make layer or dependency direction visible.", placement="inside the system body", minimum_scale="large"),
            VisualElementRequirement(element_id="owned_labels", kind="annotation_system", purpose="Attach labels to the exact system parts they explain.", placement="inside or immediately beside parts", minimum_scale="medium"),
            VisualElementRequirement(element_id="contrast_field", kind="background_field", purpose="Separate the system from explanatory evidence without UI cards.", placement="supporting canvas region", minimum_scale="large"),
        ]
    if archetype in _DATA_ARCHETYPES:
        return [
            VisualElementRequirement(element_id="evidence_anchor", kind="metric_or_chart", purpose="Make one grounded metric or comparison the first visual read.", content=takeaway, placement="dominant region", minimum_scale="hero"),
            VisualElementRequirement(element_id="comparison_context", kind="comparison", purpose="Show the baseline, category, or direction needed to interpret the evidence.", placement="adjacent to evidence", minimum_scale="medium"),
            VisualElementRequirement(element_id="meaning", kind="annotation", purpose="State what the evidence changes for the audience.", placement="same reading path", minimum_scale="medium"),
        ]
    if archetype in _JOURNEY_ARCHETYPES:
        return [
            VisualElementRequirement(element_id="continuous_path", kind="journey", purpose="Create one continuous sequence rather than disconnected cards.", content=takeaway, placement="dominant region", minimum_scale="hero"),
            VisualElementRequirement(element_id="stage_contrast", kind="progression", purpose="Use scale, position, or emphasis to differentiate stages.", placement="along the path", minimum_scale="large"),
            VisualElementRequirement(element_id="destination", kind="outcome", purpose="Make the destination visually stronger than intermediate stages.", placement="path endpoint", minimum_scale="large"),
        ]
    return [
        VisualElementRequirement(element_id="semantic_anchor", kind="editorial_visual", purpose="Turn the main claim into a visible relationship or metaphor.", content=takeaway, placement="dominant region", minimum_scale="hero"),
        VisualElementRequirement(element_id="supporting_relationship", kind="relationship", purpose="Connect supporting ideas to the main claim instead of listing them.", placement="around or beside the anchor", minimum_scale="large"),
        VisualElementRequirement(element_id="spatial_field", kind="background_field", purpose="Give the composition depth and grouping without a grid of UI panels.", placement="substantial canvas region", minimum_scale="large"),
    ]


def _merge(existing: Iterable[VisualElementRequirement], mandatory: Iterable[VisualElementRequirement]) -> List[VisualElementRequirement]:
    out: List[VisualElementRequirement] = []
    seen: set[str] = set()
    for item in [*list(mandatory), *list(existing)]:
        key = str(item.element_id or item.kind or "").strip().lower()
        if key and key not in seen:
            out.append(item)
            seen.add(key)
    return out


def enforce_visual_contract(page: PageBrief, direction: PageVisualDirection) -> PageVisualDirection:
    out = direction.model_copy(deep=True)
    mandatory = _requirements(page)
    out.required_visual_elements = _merge(out.required_visual_elements, mandatory)
    out.minimum_visual_blocks = max(len(mandatory), int(out.minimum_visual_blocks or 0))
    return out


def visual_contract_payload(page: PageBrief, direction: PageVisualDirection | None) -> Dict[str, Any]:
    resolved = enforce_visual_contract(page, direction or PageVisualDirection(page_id=page.page_id))
    return {
        "minimum_meaningful_visuals": resolved.minimum_visual_blocks,
        "required_roles": [item.model_dump() for item in resolved.required_visual_elements],
        "counting_rule": "Only semantic icons, images, charts, integrated diagrams, meaningful fields, and relationship connectors count.",
        "non_counting_elements": ["empty circles", "random dots", "thin separators", "borders", "empty rectangles", "UI tabs"],
        "composition_rule": "At least one required role must occupy 28-55% of the canvas and act as the unmistakable visual anchor.",
        "icon_rule": "Every icon must form one unit with its label or explanation; match scale, baseline, spacing, and color role.",
    }


__all__ = ["enforce_visual_contract", "visual_contract_payload"]
