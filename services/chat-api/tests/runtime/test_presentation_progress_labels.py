from app.services.presentation.contracts import PageBrief
from app.services.presentation.freeform_page_planner import FreeformPagePlanner


def test_progress_page_label_keeps_full_core_conclusion() -> None:
    conclusion = "MOVO 不是单点 AI 工具，而是统一、可控、可治理的企业智能体平台"
    brief = PageBrief(page_type="content", key_takeaway=conclusion)
    assert FreeformPagePlanner._progress_page_label(brief, 2) == conclusion


def test_progress_page_description_exposes_page_goal_without_duplication() -> None:
    brief = PageBrief(page_goal="解释 MOVO 如何补齐企业治理与交付能力", key_takeaway="MOVO 是企业生产层")
    assert FreeformPagePlanner._progress_page_description(brief, "MOVO 是企业生产层") == "解释 MOVO 如何补齐企业治理与交付能力"
    assert FreeformPagePlanner._progress_page_description(brief, brief.page_goal) == ""
