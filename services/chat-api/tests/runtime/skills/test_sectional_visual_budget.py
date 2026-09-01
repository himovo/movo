from app.enterprise_capabilities.content.writer_engine.visual_budget import resolve_sectional_visual_budget


def test_explicit_visual_bounds_are_preserved():
    budget = resolve_sectional_visual_budget(
        visual_policy={"min_visuals_per_report": 3, "max_visuals_per_report": 5},
        visual_plan={"required": True},
        section_count=10,
    )

    assert budget == {"min_visuals": 3, "max_visuals": 5}


def test_visual_intent_without_count_gets_adaptive_sectional_budget():
    budget = resolve_sectional_visual_budget(
        visual_policy={"min_visuals_per_report": 0, "max_visuals_per_report": 0},
        visual_plan={"required": True, "assets": [{"role": "visual_requirement"}]},
        section_count=7,
    )

    assert budget == {"min_visuals": 1, "max_visuals": 4}


def test_no_visual_intent_keeps_images_disabled():
    budget = resolve_sectional_visual_budget(
        visual_policy={},
        visual_plan={"required": False, "assets": []},
        section_count=8,
    )

    assert budget == {"min_visuals": 0, "max_visuals": 0}


def test_max_only_visual_request_still_generates_at_least_one_image():
    budget = resolve_sectional_visual_budget(
        visual_policy={"max_visuals_per_report": 3},
        visual_plan={"required": True},
        section_count=6,
    )

    assert budget == {"min_visuals": 1, "max_visuals": 3}
