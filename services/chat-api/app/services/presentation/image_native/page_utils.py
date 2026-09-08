from __future__ import annotations

import re

from app.services.presentation.contracts import FreeformDeckBlueprint, PageBrief


def progress_page_label(page: PageBrief, index: int) -> str:
    page_type = str(page.page_type or "").strip().lower()
    if page_type == "cover":
        return "封面"
    if page_type in {"closing", "thank_you", "thankyou", "back_cover"}:
        return "结束页"
    for value in (page.key_takeaway, page.source_outline_section, page.visual_center):
        label = _normalize_label(str(value or ""))
        if label:
            return label.rstrip("：:，,。.;；")
    return f"第{index}页"


def renumber_pages(blueprint: FreeformDeckBlueprint) -> FreeformDeckBlueprint:
    out = blueprint.model_copy(deep=True)
    pages = list(out.pages or [])
    id_map: dict[str, str] = {}
    for index, page in enumerate(pages, start=1):
        old_id = str(page.page_id or "").strip()
        page.page_id = f"page_{index:02d}"
        id_map[old_id] = page.page_id
    runtime = dict(out.runtime or {})
    for report in list(runtime.get("repair_reports") or []):
        if isinstance(report, dict) and report.get("page_id") in id_map:
            report["page_id"] = id_map[report["page_id"]]
    deck_brief = runtime.get("deck_brief")
    if isinstance(deck_brief, dict):
        for brief in list(deck_brief.get("page_briefs") or []):
            if isinstance(brief, dict) and brief.get("page_id") in id_map:
                brief["page_id"] = id_map[brief["page_id"]]
    out.runtime = runtime
    out.pages = pages
    return out


def _normalize_label(raw: str) -> str:
    text = str(raw or "").strip()
    text = re.sub(r"\s*\|\s*purpose\s*=.*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\|\s*topics\s*=.*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*\d+\s*[\.、]\s*", "", text)
    text = re.sub(r"^\s*第\s*\d+\s*页\s*[:：\-—]\s*", "", text)
    text = re.sub(r"^\s*page\s*\d+\s*[:：\-—]\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


__all__ = ["progress_page_label", "renumber_pages"]
