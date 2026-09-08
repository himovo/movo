from __future__ import annotations

from app.services.presentation.contracts import PageBrief
from app.services.presentation.image_native.image_page_builder import ImagePageBuilder, is_image_only_page
from app.services.presentation.image_native.page_copy import normalized_final_texts, source_texts_from_page
from app.services.presentation.image_native.prompt_builder import constrain_full_slide_prompt


def _page_plan() -> dict:
    return {
        "page_id": "page_01",
        "page_type": "content",
        "key_takeaway": "AI Agent进入规模化落地阶段",
        "visual_intent": "professional editorial infographic",
        "planned_texts": [
            {"id": "title", "role": "title", "text": "AI Agent进入规模化落地阶段", "priority": 10},
            {"id": "fact_1", "role": "body", "text": "企业关注执行能力与数据安全", "priority": 7},
        ],
    }


def test_image_page_contains_exactly_one_full_slide_image() -> None:
    page = ImagePageBuilder().build(
        page_plan=_page_plan(),
        source_slide_image_url="https://example.test/slide.png",
    )

    assert is_image_only_page(page)
    assert page.layout_type == "image_native_full_slide"
    assert len(page.blocks) == 1
    assert page.blocks[0].type == "image"
    assert page.blocks[0].content == "https://example.test/slide.png"
    assert page.blocks[0].w == 1
    assert page.blocks[0].h == 1

    legacy = page.model_copy(deep=True)
    legacy.layout_type = "image_native_hybrid"
    assert not is_image_only_page(legacy)


def test_image_prompt_renders_exact_copy_and_rejects_overdecorated_style() -> None:
    prompt = constrain_full_slide_prompt(
        "Create a strategy presentation slide.",
        final_texts=_page_plan()["planned_texts"],
    )

    assert "AI Agent进入规模化落地阶段" in prompt
    assert "there will be no later text overlay or reconstruction" in prompt
    assert "restrained, professional editorial presentation style" in prompt
    assert "Avoid neon glow" in prompt
    assert "Never draw blank placeholder cards" in prompt
    assert "NO letters" not in prompt
    assert "NO-TEXT" not in prompt


def test_source_copy_excludes_internal_design_instructions_and_is_bounded() -> None:
    brief = PageBrief(
        page_id="page_01",
        page_type="content",
        page_goal="让管理层理解为什么现在必须行动",
        key_takeaway="现在必须启动企业级AI治理",
        visual_intent="使用华丽霓虹科技图",
        must_include=[f"事实{i}" for i in range(1, 9)],
    )
    source = source_texts_from_page(brief)
    final = normalized_final_texts(source, fallback=[])

    rendered = [item["text"] for item in final]
    assert brief.page_goal not in rendered
    assert brief.visual_intent not in rendered
    assert rendered[0] == brief.key_takeaway
    assert len(final) <= 6
