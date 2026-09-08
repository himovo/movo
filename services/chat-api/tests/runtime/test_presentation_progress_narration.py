from app.services.presentation.contracts import DeckBrief, PageBrief, StoryDeckPlan, StoryPageSpec
from app.services.presentation.image_native.progress_narration import (
    page_generation_summary,
    presentation_ready_summary,
    preview_assembly_summary,
    story_plan_summary,
    story_planning_introduction,
    visual_plan_summary,
)


def test_progress_narration_explains_decisions_instead_of_exposing_pipeline_labels() -> None:
    story = StoryDeckPlan(
        deck_id="deck-a",
        deck_goal="介绍企业智能体",
        target_audience="企业管理者",
        pages=[
            StoryPageSpec(
                page_id="page-1",
                page_index=1,
                page_type="cover",
                communication_goal="建立主题认知",
                key_message="智能体从聊天走向执行",
                visual_intent="趋势与业务场景",
                narrative_role="opening",
            ),
            StoryPageSpec(
                page_id="page-2",
                page_index=2,
                page_type="thank_you",
                communication_goal="形成行动共识",
                key_message="现在启动高价值场景试点",
                visual_intent="行动路线",
                narrative_role="closing",
            ),
        ],
    )
    page = PageBrief(
        page_id="page-1",
        page_index=1,
        page_type="cover",
        page_goal="建立主题认知",
        key_takeaway="智能体从聊天走向执行",
        visual_center="市场增长与企业应用场景",
    )
    deck = DeckBrief(
        deck_id="deck-a",
        theme_factory_name="tech-innovation",
        visual_direction=["明亮克制", "数据与场景结合"],
        page_briefs=[page],
    )

    messages = [
        story_planning_introduction(),
        story_plan_summary(story),
        visual_plan_summary(deck, concurrency=2),
        page_generation_summary(page, index=1, total=2),
        preview_assembly_summary(2),
        presentation_ready_summary(2),
    ]

    assert all("正在" not in message for message in messages)
    assert all("image-native" not in message for message in messages)
    assert "从「智能体从聊天走向执行」切入" in messages[1]
    assert "克制的科技商务风格" in messages[2]
    assert "第 1/2 页「封面」" in messages[3]
    assert "预览与导出使用同一套画面" in messages[4]
