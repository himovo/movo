from app.services.presentation.contracts import ConstraintBundle, DeckBrief, PageBrief
from app.services.presentation.generative_design.composition_references import composition_references
from app.services.presentation.generative_design.contracts import DeckVisualPlan, PageVisualDirection
from app.services.presentation.generative_design.deck_visual_director import DeckVisualDirector
from app.services.presentation.generative_design.page_payload import build_page_composition_payload
from app.services.presentation.generative_design.surface_rhythm import build_surface_rhythm
from app.services.presentation.generative_design.visual_contract import (
    enforce_visual_contract,
    visual_contract_payload,
)


def _page(**overrides) -> PageBrief:
    values = {
        "page_id": "page_01",
        "page_index": 1,
        "page_type": "content",
        "key_takeaway": "MOVO 将 DSH 带入企业生产环境",
        "layout_archetype_id": "dominant_panel",
        "layout_family": "editorial",
    }
    values.update(overrides)
    return PageBrief.model_validate(values)


def _deck(*pages: PageBrief) -> DeckBrief:
    return DeckBrief.model_validate({
        "deck_id": "deck-a",
        "deck_goal": "解释 MOVO 价值",
        "page_briefs": [page.model_dump() for page in pages],
    })


def test_cover_contract_requires_semantic_scene_not_empty_decoration() -> None:
    page = _page(page_type="cover", layout_archetype_id="full_bleed_visual")
    contract = visual_contract_payload(page, PageVisualDirection(page_id=page.page_id))

    assert contract["minimum_meaningful_visuals"] >= 3
    assert contract["required_roles"][0]["element_id"] == "semantic_hero"
    assert "empty circles" in contract["non_counting_elements"]
    assert "28-55%" in contract["composition_rule"]


def test_system_contract_upgrades_weak_llm_direction() -> None:
    page = _page(layout_archetype_id="architecture_blueprint", layout_family="process_system")
    weak = PageVisualDirection(page_id=page.page_id, minimum_visual_blocks=1)

    resolved = enforce_visual_contract(page, weak)

    roles = {item.element_id for item in resolved.required_visual_elements}
    assert resolved.minimum_visual_blocks >= 4
    assert {"system_body", "dependency_logic", "owned_labels", "contrast_field"} <= roles


def test_composition_references_are_quality_grammar_not_templates() -> None:
    references = composition_references("architecture_blueprint")

    assert references[0]["name"] == "system_cutaway"
    assert "coordinates" not in str(references).lower()
    assert "boxes connected by loose wires" in references[0]["avoid"]


def test_surface_rhythm_changes_contrast_across_deck() -> None:
    pages = [
        _page(page_id="cover", page_index=1, page_type="cover"),
        _page(page_id="architecture", page_index=2, layout_family="process_system"),
        _page(page_id="evidence", page_index=3, layout_family="comparison_data"),
        _page(page_id="close", page_index=4, page_type="thank_you"),
    ]

    modes = [item["mode"] for item in build_surface_rhythm(_deck(*pages))]

    assert modes == ["dark_hero", "light_blueprint", "light_evidence", "dark_resolution"]


def test_page_payload_carries_generation_quality_inputs() -> None:
    page = _page(layout_archetype_id="architecture_blueprint", layout_family="process_system")
    deck = _deck(page)
    plan = DeckVisualPlan(
        deck_id=deck.deck_id,
        page_directions=[enforce_visual_contract(page, PageVisualDirection(page_id=page.page_id))],
    )

    payload = build_page_composition_payload(
        deck_brief=deck,
        page_brief=page,
        constraint_bundle=ConstraintBundle(),
        visual_plan=plan,
        recent_pages=[],
    )

    assert payload["visual_contract"]["minimum_meaningful_visuals"] >= 4
    assert payload["composition_references"][0]["name"] == "system_cutaway"
    assert payload["surface_rhythm"]["mode"] == "dark_focus"


def test_visual_director_completion_enforces_contract() -> None:
    page = _page(page_type="cover", layout_archetype_id="full_bleed_visual")
    deck = _deck(page)
    candidate = DeckVisualPlan(
        deck_id="wrong",
        page_directions=[PageVisualDirection(page_id=page.page_id, minimum_visual_blocks=1)],
    )

    completed = DeckVisualDirector()._complete(candidate=candidate, deck_brief=deck)

    direction = completed.for_page(page.page_id)
    assert direction is not None
    assert direction.minimum_visual_blocks >= 3
    assert direction.required_visual_elements[0].element_id == "semantic_hero"
