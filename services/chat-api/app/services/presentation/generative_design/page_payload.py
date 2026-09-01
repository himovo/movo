from __future__ import annotations

from typing import Any, Dict, List

from app.services.presentation.contracts import ConstraintBundle, DeckBrief, PageBrief
from app.services.presentation.layout_archetypes.catalog import archetype_by_id
from app.services.presentation.icon_library import available_icon_names

from .content_packet import build_content_packet
from .contracts import DeckVisualPlan


def build_page_composition_payload(
    *,
    deck_brief: DeckBrief,
    page_brief: PageBrief,
    constraint_bundle: ConstraintBundle,
    visual_plan: DeckVisualPlan,
    recent_pages: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Small, non-duplicative input for the holistic page composer."""
    spec = archetype_by_id(str(page_brief.layout_archetype_id or "dominant_panel").strip())
    direction = visual_plan.for_page(str(page_brief.page_id or "").strip())
    return {
        "deck_context": {
            "goal": str(deck_brief.deck_goal or "").strip(),
            "audience": str(deck_brief.target_audience or "").strip(),
            "language": str(deck_brief.language or "zh-CN").strip(),
            "user_design_guidance": str(deck_brief.user_generation_guidance or "").strip(),
            "design_tokens": deck_brief.design_tokens.model_dump(),
            "visual_language": visual_plan.compact_payload(),
        },
        "content_packet": build_content_packet(
            page_brief=page_brief,
            constraint_bundle=constraint_bundle,
        ),
        "page_visual_direction": direction.model_dump() if direction is not None else {},
        "assigned_layout": {
            "archetype_id": spec.archetype_id,
            "family": spec.family,
            "design_brief": spec.prompt_brief,
            "must_do": list(spec.must_do),
            "must_avoid": list(spec.must_avoid),
        },
        "authoring_capabilities": {
            "icon_names": list(available_icon_names()),
            "text_container_binding": {
                "container_id": "id of the owning group or shape",
                "coordinate_space": "parent for children inside that owner",
                "auto_fit": "true only when the text box may grow within its owner",
            },
        },
        "continuity": {
            "previous_pages": list(recent_pages or [])[-2:],
            "relation_to_previous": str(page_brief.relation_to_previous or "").strip(),
            "relation_to_next": str(page_brief.relation_to_next or "").strip(),
        },
    }


__all__ = ["build_page_composition_payload"]
