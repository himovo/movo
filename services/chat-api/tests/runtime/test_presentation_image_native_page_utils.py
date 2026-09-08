from app.services.presentation.contracts import PageBrief
from app.services.presentation.image_native.page_utils import progress_page_label


def test_progress_page_label_uses_business_conclusion() -> None:
    conclusion = "MOVO 是 DSH 进入企业生产环境的完整平台"
    brief = PageBrief(page_id="page_02", page_index=2, key_takeaway=conclusion)

    assert progress_page_label(brief, 2) == conclusion


def test_progress_page_label_names_cover_and_closing_pages() -> None:
    assert progress_page_label(PageBrief(page_id="cover", page_index=1, page_type="cover"), 1) == "封面"
    assert progress_page_label(PageBrief(page_id="closing", page_index=8, page_type="closing"), 8) == "结束页"
