import asyncio

from app.services.presentation.contracts import ConstraintBundle, DeckBrief, PageBrief, StoryDeckPlan
from app.services.presentation.generative_design.composition_grammar import fallback_deck_visual_plan
from app.services.presentation.generative_design.content_packet import build_content_packet
from app.services.presentation.generative_design.contracts import (
    DeckVisualPlan,
    PageVisualDirection,
    VisualElementRequirement,
)
from app.services.presentation.generative_design.deck_visual_director import DeckVisualDirector
from app.services.presentation.generative_design.prompts import (
    build_deck_visual_direction_prompt,
    build_page_composition_prompt,
)


def _deck() -> DeckBrief:
    return DeckBrief.model_validate({
        "deck_id": "deck-a",
        "deck_goal": "解释平台价值",
        "target_audience": "CIO",
        "page_briefs": [
            {
                "page_id": "page_01",
                "page_index": 1,
                "page_type": "cover",
                "key_takeaway": "统一平台",
                "layout_archetype_id": "full_bleed_visual",
            },
            {
                "page_id": "page_02",
                "page_index": 2,
                "page_type": "content",
                "key_takeaway": "从目标到成果",
                "must_include": ["理解目标", "规划执行", "验证交付"],
                "layout_archetype_id": "progressive_arrow_chain",
            },
        ],
    })


def _story() -> StoryDeckPlan:
    return StoryDeckPlan.model_validate({
        "deck_id": "deck-a",
        "deck_goal": "解释平台价值",
        "target_audience": "CIO",
        "pages": [],
    })


def test_fallback_visual_plan_has_distinct_whole_page_directions() -> None:
    visual_plan = fallback_deck_visual_plan(_deck())

    assert [item.page_id for item in visual_plan.page_directions] == ["page_01", "page_02"]
    assert visual_plan.page_directions[0].composition != visual_plan.page_directions[1].composition
    assert all(item.accent_edge == "none" for item in visual_plan.page_directions)
    assert "whole-page editorial infographic composition" in visual_plan.design_language


def test_visual_director_fills_missing_page_directions(monkeypatch) -> None:
    from app.services.presentation.generative_design import deck_visual_director as module

    async def fake_invoke_structured(**kwargs):
        return DeckVisualPlan(
            deck_id="wrong",
            design_language=["editorial"],
            page_directions=[
                PageVisualDirection(page_id="page_01", composition="hero_scene"),
            ],
        )

    monkeypatch.setattr(module, "invoke_structured", fake_invoke_structured)
    result = asyncio.run(DeckVisualDirector().plan(deck_brief=_deck(), story_plan=_story()))

    assert result.deck_id == "deck-a"
    assert [item.page_id for item in result.page_directions] == ["page_01", "page_02"]
    assert result.page_directions[1].composition == "progressive_directional_chain"


def test_content_packet_is_semantic_not_card_shaped() -> None:
    page = _deck().page_briefs[1]
    packet = build_content_packet(
        page_brief=page,
        constraint_bundle=ConstraintBundle(tool_observations=[{
            "evidence_id": "ev-1",
            "source_label": "内部知识",
            "summary": "MOVO 负责企业级交付",
        }]),
    )

    assert "cards" not in packet
    assert packet["supporting_ideas"] == ["理解目标", "规划执行", "验证交付"]
    assert packet["evidence"][0]["evidence_id"] == "ev-1"


def test_generation_prompts_prioritize_composition_over_validation() -> None:
    deck_prompt = build_deck_visual_direction_prompt()
    page_prompt = build_page_composition_prompt(repair_mode=False)

    assert "whole-page composition" in deck_prompt
    assert "editorial infographic" in page_prompt
    assert "wall of identical rounded rectangles" in page_prompt
    assert "Every content card/group MUST" not in page_prompt
    assert "border_left" not in page_prompt
    assert "required_visual_elements" in deck_prompt
    assert "Style keys MUST use snake_case only" in page_prompt
    assert "Text and its visual container are one composition unit" in page_prompt
    assert "Never output placeholder metrics" in page_prompt
    assert "Repeated sparkle icons" in page_prompt
    assert "authoring_capabilities.icon_names" in page_prompt
    assert "container_id" in page_prompt
    assert "Reserve a clean headline zone" in page_prompt
    assert "Treat icon and copy as one semantic unit" in page_prompt
    assert "65-85%" in page_prompt
    assert "iconography rhythm" in deck_prompt


def test_visual_director_can_override_deterministic_layout() -> None:
    deck = _deck()
    plan = fallback_deck_visual_plan(deck)
    direction = plan.for_page("page_02")
    assert direction is not None
    direction.recommended_archetype = "radial_feature_ring"
    direction.required_visual_elements = [
        VisualElementRequirement(kind="diagram", purpose="Show the platform at the center")
    ]

    updated = DeckVisualDirector().apply_layout_recommendations(deck_brief=deck, visual_plan=plan)

    page = updated.page_briefs[1]
    assert page.layout_archetype_id == "radial_feature_ring"
    assert page.layout_family == "process_system"
    assert page.layout_constraints["archetype_id"] == "radial_feature_ring"
