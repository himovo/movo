from app.services.presentation.contracts import FreeformBlock, FreeformPageBlueprint
from app.services.presentation.layout_archetypes.conformance import layout_conformance_issues
from app.services.presentation.layout_archetypes.recovery import build_content_safe_page
from app.services.presentation.contracts import PageBrief


def _text(block_id: str, x: float, content: str) -> FreeformBlock:
    return FreeformBlock(id=block_id, type="text_box", x=x, y=0.2, w=0.35, h=0.1, content=content)


def test_conformance_rejects_wrong_layout_type() -> None:
    page = FreeformPageBlueprint(
        page_id="page_01",
        layout_type="card_grid",
        blocks=[_text("left", 0.05, "现状"), _text("right", 0.55, "目标")],
    )
    issues = layout_conformance_issues(page, expected_archetype_id="left_right_comparison")
    assert "layout_type_must_equal:left_right_comparison" in issues


def test_data_layout_requires_chart_or_visible_metrics() -> None:
    page = FreeformPageBlueprint(
        page_id="page_01",
        layout_type="data_dashboard",
        blocks=[_text("a", 0.05, "经营情况"), _text("b", 0.55, "保持增长")],
    )
    assert "assigned_layout_requires_chart_or_metrics" in layout_conformance_issues(
        page,
        expected_archetype_id="data_dashboard",
    )


def test_data_layout_accepts_two_metrics() -> None:
    page = FreeformPageBlueprint(
        page_id="page_01",
        layout_type="big_number_row",
        blocks=[_text("a", 0.05, "+30%"), _text("b", 0.55, "3.2x")],
    )
    assert layout_conformance_issues(page, expected_archetype_id="big_number_row") == []


def test_legacy_text_aliases_are_not_misclassified_as_empty() -> None:
    page = FreeformPageBlueprint(
        page_id="page_01",
        layout_type="dominant_panel",
        blocks=[
            FreeformBlock(id="title", type="title", x=0.1, y=0.1, w=0.8, h=0.2, content="核心结论"),
            FreeformBlock(id="body", type="paragraph", x=0.1, y=0.4, w=0.8, h=0.3, content="这是完整的说明性文字。"),
        ],
    )
    assert layout_conformance_issues(page, expected_archetype_id="dominant_panel") == []


def test_content_safe_recovery_preserves_page_copy() -> None:
    brief = PageBrief(
        page_id="page_07",
        page_goal="采用三阶段推进路径",
        key_takeaway="从试点验证走向平台化运营",
        must_include=["第一阶段：试点验证", "第二阶段：场景推广", "第三阶段：平台化运营"],
    )
    page = build_content_safe_page(brief)
    all_text = "\n".join(str(block.content or "") for block in page.blocks)
    assert page.layout_type == "dominant_panel"
    assert "从试点验证走向平台化运营" in all_text
    assert "第三阶段：平台化运营" in all_text
    assert layout_conformance_issues(page, expected_archetype_id="dominant_panel") == []
