from __future__ import annotations

from typing import Dict

from app.services.presentation.contracts import DeckBrief, PageBrief

from .contracts import DeckVisualPlan, PageVisualDirection, VisualElementRequirement


_COMPOSITIONS: Dict[str, dict[str, str]] = {
    "full_bleed_visual": {
        "composition": "full_canvas_editorial_statement",
        "anchor": "oversized thesis or one integrated hero visual",
        "regions": "one dominant field; one compact context zone",
        "surface": "full_bleed_or_open_canvas",
    },
    "dominant_panel": {
        "composition": "one_dominant_visual_argument",
        "anchor": "one large claim, diagram, or visual metaphor",
        "regions": "one hero region; restrained supporting evidence",
        "surface": "flat_editorial",
    },
    "asymmetric_split": {
        "composition": "asymmetric_editorial_split",
        "anchor": "one visually dominant side balanced by a lighter side",
        "regions": "unequal left and right fields with one reading direction",
        "surface": "open_canvas_with_one_filled_field",
    },
    "left_right_comparison": {
        "composition": "aligned_two_world_comparison",
        "anchor": "the contrast between two clearly distinct systems",
        "regions": "two aligned fields connected by shared criteria",
        "surface": "flat_comparison",
    },
    "split_screen_dual": {
        "composition": "two_full_height_worlds",
        "anchor": "a strong visual boundary between current and target states",
        "regions": "two contrasting full-height fields",
        "surface": "split_color_fields",
    },
    "radial_feature_ring": {
        "composition": "center_with_four_or_five_satellites",
        "anchor": "one central platform or idea",
        "regions": "one center; supporting regions distributed around it",
        "surface": "open_canvas_diagram",
    },
    "architecture_blueprint": {
        "composition": "layered_system_with_cross_cutting_control",
        "anchor": "the dependency between substantial system layers",
        "regions": "three to six layers plus an optional cross-cutting rail",
        "surface": "structured_flat_diagram",
    },
    "stacked_system": {
        "composition": "stacked_dependency_system",
        "anchor": "a clear foundation-to-experience progression",
        "regions": "three to six broad stacked bands",
        "surface": "layered_color_fields",
    },
    "layered_band": {
        "composition": "broad_responsibility_bands",
        "anchor": "ordered layers with labels inside substantial bands",
        "regions": "three to six broad horizontal or vertical bands",
        "surface": "flat_bands",
    },
    "timeline_spine": {
        "composition": "single_editorial_timeline",
        "anchor": "one continuous time spine and a highlighted destination",
        "regions": "three to five milestones on one path",
        "surface": "open_canvas_timeline",
    },
    "progressive_arrow_chain": {
        "composition": "progressive_directional_chain",
        "anchor": "one visible movement from low to high maturity",
        "regions": "three to five connected stages with increasing weight",
        "surface": "directional_shapes",
    },
    "icon_feature_row": {
        "composition": "large_symbol_feature_sequence",
        "anchor": "a concise thesis supported by three to five large symbols",
        "regions": "one headline field; one aligned symbol-led row",
        "surface": "flat_iconographic",
    },
    "card_grid": {
        "composition": "disciplined_peer_module_field",
        "anchor": "one highlighted capability within a restrained peer system",
        "regions": "a real grid only when the ideas are semantically equal",
        "surface": "light_modules_without_repeated_side_rails",
    },
    "data_dashboard": {
        "composition": "editorial_data_story",
        "anchor": "one decisive metric or chart, not a wall of KPI cards",
        "regions": "one data hero; one interpretation zone; optional support metrics",
        "surface": "data_first_open_canvas",
    },
    "big_number_row": {
        "composition": "oversized_metric_sequence",
        "anchor": "two to four oversized numbers",
        "regions": "one clean metric row with a short implication",
        "surface": "typographic_data",
    },
    "stats_plus_narrative": {
        "composition": "metric_and_meaning_split",
        "anchor": "a compact metric field paired with an explanatory story",
        "regions": "one metric side; one narrative side",
        "surface": "editorial_data_split",
    },
    "structured_matrix": {
        "composition": "explicit_axis_matrix",
        "anchor": "the matrix logic and one emphasized cell or path",
        "regions": "clear row and column meaning with concise cells",
        "surface": "flat_matrix",
    },
    "numbered_list": {
        "composition": "oversized_ordinal_sequence",
        "anchor": "large ordinal typography and a clean vertical rhythm",
        "regions": "three to five rows without enclosing every row in a card",
        "surface": "typographic_list",
    },
    "accent_callout": {
        "composition": "decision_statement_with_action_path",
        "anchor": "one bold decision or next action",
        "regions": "one hero statement; one compact action structure",
        "surface": "editorial_callout",
    },
    "hero_statement": {
        "composition": "oversized_statement_and_whitespace",
        "anchor": "one sentence dominates the canvas",
        "regions": "one statement field; optional small context mark",
        "surface": "open_typographic_canvas",
    },
    "top_hero_bottom_detail": {
        "composition": "top_thesis_bottom_evidence",
        "anchor": "a strong upper thesis followed by restrained evidence",
        "regions": "one broad top field; one compact lower field",
        "surface": "editorial_bands",
    },
    "image_text_split": {
        "composition": "visual_and_narrative_split",
        "anchor": "one substantial visual paired with concise narration",
        "regions": "one visual field; one text field",
        "surface": "media_editorial",
    },
    "alternating_zigzag": {
        "composition": "alternating_visual_journey",
        "anchor": "a clear journey that changes side as it progresses",
        "regions": "three or four alternating steps",
        "surface": "open_process_canvas",
    },
    "sidebar_toc": {
        "composition": "section_index_and_focus",
        "anchor": "the active section and one focused content field",
        "regions": "one slim index; one broad content area",
        "surface": "editorial_navigation",
    },
    "quote_spotlight": {
        "composition": "single_insight_spotlight",
        "anchor": "one human-scale insight with generous whitespace",
        "regions": "one quotation field; one attribution or implication",
        "surface": "open_typographic_canvas",
    },
}


def fallback_page_direction(page: PageBrief) -> PageVisualDirection:
    spec = _COMPOSITIONS.get(str(page.layout_archetype_id or "").strip(), _COMPOSITIONS["dominant_panel"])
    page_type = str(page.page_type or "content").strip().lower()
    avoid = [
        "dashboard-like UI chrome",
        "repeating the same rounded card treatment across the page",
        "colored left-edge rails as a default decoration",
        "many equal-weight boxes without one visual anchor",
    ]
    card_policy = (
        "no content cards; use one integrated composition"
        if page_type in {"cover", "section_divider", "thank_you"}
        else "use cards only for genuinely peer content; otherwise use open regions, bands, symbols, or relationships"
    )
    return PageVisualDirection(
        page_id=str(page.page_id or "").strip(),
        composition=spec["composition"],
        visual_story=str(page.composition_intent or page.visual_intent or page.key_takeaway or "").strip(),
        visual_anchor=spec["anchor"],
        reading_flow="left_to_right" if "horizontal" in spec["regions"] or "left" in spec["regions"] else "top_to_bottom",
        region_plan=[part.strip() for part in spec["regions"].split(";") if part.strip()],
        surface_treatment=spec["surface"],
        illustration_language="large editable vector symbols and simple visual metaphors",
        decoration_language="sparse dot fields, soft waves, directional arrows, or quiet geometry chosen for this page",
        typography_move="one large takeaway with short labels and no paragraph walls",
        card_policy=card_policy,
        accent_edge="none",
        avoid_patterns=avoid,
        recommended_archetype=str(page.layout_archetype_id or "dominant_panel").strip() or "dominant_panel",
        required_visual_elements=[
            VisualElementRequirement(
                element_id="primary_anchor",
                kind="hero_symbol" if page_type in {"cover", "section_divider", "thank_you"} else "diagram",
                purpose="Turn the primary claim into one visible visual argument, not a text list.",
                content=str(page.key_takeaway or page.visual_intent or "").strip(),
                placement="dominant_region",
                minimum_scale="large",
            )
        ],
        minimum_visual_blocks=1,
    )


def fallback_deck_visual_plan(deck: DeckBrief) -> DeckVisualPlan:
    return DeckVisualPlan(
        deck_id=str(deck.deck_id or "presentation").strip() or "presentation",
        design_thesis=(
            "An editorial enterprise presentation that uses complete visual scenes, large hierarchy, "
            "directional relationships, and restrained vector decoration instead of dashboard card walls."
        ),
        design_language=[
            "whole-page editorial infographic composition",
            "clear visual anchor and reading path on every page",
            "large scale contrast between primary and supporting content",
            "flat open canvas with selective filled fields",
        ],
        rhythm_rules=[
            "Adjacent pages must change silhouette, visual anchor position, and primary composition.",
            "Do not repeat a header-plus-card-grid formula across the deck.",
            "Use cards only when peer comparison is the actual information model.",
            "Use large directional arrows, layered fields, oversized type, or visual metaphors where they tell the story better.",
        ],
        page_directions=[fallback_page_direction(page) for page in list(deck.page_briefs or [])],
    )


__all__ = ["fallback_deck_visual_plan", "fallback_page_direction"]
