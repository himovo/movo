import pytest

from app.services.presentation.contracts import DeckBrief, StoryDeckPlan
from app.services.presentation.layout_archetypes import ARCHETYPE_CATALOG
from app.services.presentation.layout_archetypes.planner import LayoutAssignmentPlanner


def _deck_and_story():
    intents = [
        "introduce_topic",
        "frame_problem",
        "explain_solution",
        "compare_options",
        "show_architecture",
        "show_process",
        "show_roadmap",
        "show_metrics",
        "show_case",
        "ask_for_decision",
    ]
    texts = [
        "企业战略封面",
        "业务问题与核心洞察",
        "产品能力与功能模块",
        "新旧方案对比差异",
        "系统架构与模块分层",
        "落地流程与实施步骤",
        "演进路线与关键里程碑",
        "核心指标增长与 ROI",
        "客户案例与业务场景",
        "行动建议与决策",
    ]
    briefs = []
    stories = []
    for index, (intent, text) in enumerate(zip(intents, texts), start=1):
        page_type = "cover" if index == 1 else "content"
        briefs.append({
            "page_id": f"page_{index:02d}",
            "page_index": index,
            "page_type": page_type,
            "page_goal": text,
            "key_takeaway": text,
            "visual_intent": text,
            "composition_intent": text,
            "must_include": ["要点一", "要点二", "要点三"],
            "validation_profile": intent,
        })
        stories.append({
            "page_id": f"page_{index:02d}",
            "page_index": index,
            "page_type": page_type,
            "communication_goal": text,
            "key_message": text,
            "visual_intent": text,
            "narrative_role": "body",
            "page_intent": intent,
        })
    return (
        DeckBrief.model_validate({"deck_id": "deck-a", "page_briefs": briefs}),
        StoryDeckPlan.model_validate({
            "deck_id": "deck-a",
            "deck_goal": "企业方案",
            "target_audience": "CIO",
            "pages": stories,
        }),
    )


def test_assignment_is_deterministic_and_diverse() -> None:
    deck, story = _deck_and_story()
    planner = LayoutAssignmentPlanner()
    first = planner.assign(deck, story)
    second = planner.assign(deck, story)
    first_ids = [page.layout_archetype_id for page in first.page_briefs]
    second_ids = [page.layout_archetype_id for page in second.page_briefs]
    assert first_ids == second_ids
    assert len(set(first_ids)) >= 6
    assert all(left != right for left, right in zip(first_ids, first_ids[1:]))
    assert max(first.layout_distribution.values()) <= 2


def test_assignment_matches_real_page_semantics() -> None:
    deck, story = _deck_and_story()
    assigned = LayoutAssignmentPlanner().assign(deck, story)
    by_id = {page.page_id: page.layout_archetype_id for page in assigned.page_briefs}
    assert by_id["page_01"] == "full_bleed_visual"
    assert by_id["page_04"] in {"left_right_comparison", "split_screen_dual"}
    assert by_id["page_05"] == "architecture_blueprint"
    assert by_id["page_07"] in {"timeline_spine", "progressive_arrow_chain"}
    assert by_id["page_08"] in {"data_dashboard", "big_number_row", "stats_plus_narrative"}
    assert by_id["page_09"] == "image_text_split"


def test_qualitative_improvement_does_not_force_ungrounded_data_layout() -> None:
    deck = DeckBrief.model_validate({
        "deck_id": "qualitative-outcome",
        "page_briefs": [{
            "page_id": "page_01",
            "page_index": 1,
            "page_type": "content",
            "page_goal": "展示业务成效",
            "key_takeaway": "平台让知识工作效率显著提升",
            "must_include": ["信息获取更主动", "跨团队协作更顺畅", "知识复用更充分"],
            "validation_profile": "show_metrics",
        }],
    })
    story = StoryDeckPlan.model_validate({
        "deck_id": "qualitative-outcome",
        "deck_goal": "MOVO 业务价值",
        "target_audience": "CIO",
        "pages": [{
            "page_id": "page_01",
            "page_index": 1,
            "page_type": "content",
            "communication_goal": "展示业务成效",
            "key_message": "平台让知识工作效率显著提升",
            "visual_intent": "突出前后工作方式变化",
            "narrative_role": "body",
            "page_intent": "show_metrics",
        }],
    })
    assigned = LayoutAssignmentPlanner().assign(deck, story)
    selected = next(spec for spec in ARCHETYPE_CATALOG if spec.archetype_id == assigned.page_briefs[0].layout_archetype_id)
    assert selected.requires_data is False


@pytest.mark.parametrize("spec", ARCHETYPE_CATALOG, ids=lambda spec: spec.archetype_id)
def test_every_catalog_archetype_has_a_reachable_semantic_scenario(spec) -> None:
    signals = []
    if spec.requires_data:
        signals.append("核心指标增长 30% ROI 数据")
    if spec.requires_comparison:
        signals.append("新旧方案对比 before after")
    if spec.requires_sequence:
        signals.append("实施流程步骤阶段路线")
    if spec.requires_image:
        signals.append("客户案例场景图片视觉")
    text = " ".join([spec.archetype_id, *signals])
    intent = next(iter(spec.page_intents), "explain_solution")
    deck = DeckBrief.model_validate({
        "deck_id": "reachability",
        "page_briefs": [{
            "page_id": "page_01",
            "page_index": 1,
            "page_type": "content",
            "page_goal": text,
            "key_takeaway": text,
            "composition_intent": text,
            "must_include": ["一", "二", "三", "四"],
            "validation_profile": intent,
        }],
    })
    story = StoryDeckPlan.model_validate({
        "deck_id": "reachability",
        "deck_goal": text,
        "target_audience": "CIO",
        "pages": [{
            "page_id": "page_01",
            "page_index": 1,
            "page_type": "content",
            "communication_goal": text,
            "key_message": text,
            "visual_intent": text,
            "narrative_role": "body",
            "page_intent": intent,
        }],
    })
    assigned = LayoutAssignmentPlanner().assign(deck, story)
    assert assigned.page_briefs[0].layout_archetype_id == spec.archetype_id
