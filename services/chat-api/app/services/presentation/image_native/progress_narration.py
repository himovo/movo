from __future__ import annotations

import re

from app.services.presentation.contracts import DeckBrief, PageBrief, StoryDeckPlan
from app.services.presentation.image_native.page_utils import progress_page_label


_THEME_NAMES = {
    "tech-innovation": "克制的科技商务风格",
    "business-professional": "专业商务风格",
    "minimal-editorial": "简洁的编辑式风格",
    "data-storytelling": "数据叙事风格",
}


def story_planning_introduction() -> str:
    return (
        "我先梳理这份演示的叙事主线，明确受众、核心结论和每一页的分工，"
        "避免页面各自完整却前后割裂。"
    )


def story_plan_summary(story_plan: StoryDeckPlan) -> str:
    pages = list(story_plan.pages or [])
    count = len(pages)
    if not pages:
        return "叙事主线已经确定。接下来我会统一视觉语言，再把内容组织成完整页面。"

    opening = _excerpt(pages[0].key_message or pages[0].communication_goal)
    closing = _excerpt(pages[-1].key_message or pages[-1].communication_goal)
    if count == 1:
        return f"故事线已经收敛为 1 页，核心围绕「{opening}」展开；接下来会用一个清晰的视觉中心承载结论。"
    return (
        f"故事线已经整理为 {count} 页：从「{opening}」切入，到「{closing}」收束。"
        "接下来会让各页保持统一气质，同时避免重复同一种构图。"
    )


def visual_plan_summary(deck_brief: DeckBrief, *, concurrency: int) -> str:
    page_count = len(list(deck_brief.page_briefs or []))
    theme_key = str(deck_brief.theme_factory_name or "").strip().lower()
    theme = _THEME_NAMES.get(theme_key, _clean(deck_brief.theme_factory_name))
    direction = "、".join(
        item for item in (_excerpt(value, limit=30) for value in list(deck_brief.visual_direction or [])[:2]) if item
    )

    details = []
    if theme:
        details.append(f"整体采用{theme}")
    if direction:
        details.append(f"视觉重点是{direction}")
    description = "，".join(details) or "色彩、字体和画面密度将保持一致"
    generation = "并行生成" if concurrency > 1 and page_count > 1 else "逐页生成"
    return (
        f"视觉方案已经确定：{description}。{page_count} 页会按{generation}处理，"
        "每页直接生成完整画面，使文字、图形和空间关系天然融合。"
    )


def page_generation_summary(page_brief: PageBrief, *, index: int, total: int) -> str:
    label = progress_page_label(page_brief, index)
    purpose = _excerpt(
        page_brief.key_takeaway
        or page_brief.page_goal
        or page_brief.narrative_role,
        limit=52,
    )
    visual = _excerpt(
        page_brief.visual_center
        or page_brief.composition_intent
        or page_brief.visual_intent,
        limit=42,
    )

    parts = [f"第 {index}/{total} 页「{label}」"]
    if purpose and purpose != label:
        parts.append(f"负责传达「{purpose}」")
    else:
        parts.append("将承担这一段叙事的核心表达")
    if visual:
        parts.append(f"画面会围绕「{visual}」组织")
    return "，".join(parts) + "；标题、信息和视觉元素会在同一次生成中完成排版。"


def preview_assembly_summary(page_count: int) -> str:
    return (
        f"{page_count} 张页面成品图已经就绪。我现在把它们装配成可预览、可导出的 16:9 演示文稿，"
        "并确保预览与导出使用同一套画面。"
    )


def presentation_ready_summary(page_count: int) -> str:
    return (
        f"演示文稿已经完成，共 {page_count} 页。页面将以整页视觉成品交付，"
        "导出 PPT 时不会再因二次排版产生文字和图形错位。"
    )


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" ，,。.;；：:")


def _excerpt(value: object, *, limit: int = 38) -> str:
    text = _clean(value)
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip(" ，,。.;；：:") + "…"


__all__ = [
    "page_generation_summary",
    "presentation_ready_summary",
    "preview_assembly_summary",
    "story_plan_summary",
    "story_planning_introduction",
    "visual_plan_summary",
]
