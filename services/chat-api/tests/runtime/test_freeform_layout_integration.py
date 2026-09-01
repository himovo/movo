import asyncio

from app.services.presentation.contracts import (
    ComposerPageBlueprint,
    ConstraintBundle,
    DeckBrief,
    FreeformBlock,
    PageBrief,
)
from app.services.presentation.freeform_page_planner import FreeformPagePlanner


def _page(layout_type: str) -> ComposerPageBlueprint:
    return ComposerPageBlueprint(
        page_id="page_01",
        layout_type=layout_type,
        blocks=[
            FreeformBlock(id="headline", type="text_box", x=0.08, y=0.08, w=0.7, h=0.1, content="核心结论"),
            FreeformBlock(id="support", type="text_box", x=0.1, y=0.3, w=0.6, h=0.12, content="支持信息"),
        ],
    )


def _page_without_layout() -> ComposerPageBlueprint:
    page = _page("dominant_panel")
    page.layout_type = ""
    return page


def _card_grid_page() -> ComposerPageBlueprint:
    groups = []
    for index, x in enumerate((0.06, 0.36, 0.66), start=1):
        groups.append(FreeformBlock(
            id=f"card_{index}",
            type="group",
            x=x,
            y=0.25,
            w=0.26,
            h=0.45,
            children=[FreeformBlock(
                id=f"card_{index}_title",
                type="text_box",
                x=0.05,
                y=0.08,
                w=0.8,
                h=0.2,
                coordinate_space="parent",
                content=f"能力 {index}",
            )],
        ))
    return ComposerPageBlueprint(page_id="page_01", layout_type="anything", blocks=groups)


def test_compose_records_structure_mismatch_without_regenerating_page(monkeypatch) -> None:
    from app.services.presentation import freeform_page_planner as module

    calls = []

    async def fake_invoke_structured(**kwargs):
        calls.append(kwargs)
        return _page("dominant_panel")

    monkeypatch.setattr(module, "invoke_structured", fake_invoke_structured)
    planner = FreeformPagePlanner()
    page_brief = PageBrief.model_validate({
        "page_id": "page_01",
        "page_index": 1,
        "page_type": "content",
        "page_goal": "给出核心结论",
        "key_takeaway": "立即启动",
        "layout_archetype_id": "card_grid",
        "layout_family": "structured",
        "layout_constraints": {
            "archetype_id": "card_grid",
            "family": "structured",
            "design_brief": "peer card grid",
        },
    })
    deck = DeckBrief.model_validate({
        "deck_id": "deck-a",
        "page_briefs": [page_brief.model_dump()],
    })

    result = asyncio.run(
        planner._compose_page(
            deck_brief=deck,
            constraint_bundle=ConstraintBundle(),
            page_brief=page_brief,
            previous_page=None,
            next_page=None,
            prior_pages=[],
        )
    )

    assert result.layout_type == "card_grid"
    assert len(calls) == 1
    assert calls[0]["payload"]["assigned_layout"]["archetype_id"] == "card_grid"
    assert calls[0]["payload"]["page_visual_direction"]["page_id"] == "page_01"
    assert "content_packet" in calls[0]["payload"]
    assert "deck_creative_brief" not in calls[0]["payload"]
    assert "page_creative_brief" not in calls[0]["payload"]
    assert "critic_brief" not in calls[0]["payload"]
    assert "deck_context" in calls[0]["payload"]
    assert "Available archetypes (25 total" not in calls[0]["system_prompt"]
    assert "Every content card/group MUST" not in calls[0]["system_prompt"]
    assert "wall of identical rounded rectangles" in calls[0]["system_prompt"]


def test_compose_applies_movo_layout_metadata_when_model_omits_it(monkeypatch) -> None:
    from app.services.presentation import freeform_page_planner as module

    calls = []

    async def fake_invoke_structured(**kwargs):
        calls.append(kwargs)
        return _page_without_layout()

    monkeypatch.setattr(module, "invoke_structured", fake_invoke_structured)
    planner = FreeformPagePlanner()
    page_brief = PageBrief.model_validate({
        "page_id": "page_01",
        "page_index": 1,
        "page_type": "content",
        "page_goal": "给出核心结论",
        "layout_archetype_id": "dominant_panel",
        "layout_family": "editorial",
        "layout_constraints": {"archetype_id": "dominant_panel"},
    })
    deck = DeckBrief.model_validate({"deck_id": "deck-a", "page_briefs": [page_brief.model_dump()]})

    result = asyncio.run(planner._compose_page(
        deck_brief=deck,
        constraint_bundle=ConstraintBundle(),
        page_brief=page_brief,
        previous_page=None,
        next_page=None,
        prior_pages=[],
    ))

    assert result.layout_type == "dominant_panel"
    assert len(calls) == 1
