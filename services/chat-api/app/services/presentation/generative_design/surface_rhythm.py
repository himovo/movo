from __future__ import annotations

from typing import Any, Dict, List

from app.services.presentation.contracts import DeckBrief, PageBrief


def _mode(page: PageBrief, index: int) -> str:
    page_type = str(page.page_type or "content").strip().lower()
    family = str(page.layout_family or "").strip().lower()
    if page_type == "cover":
        return "dark_hero"
    if page_type == "section_divider":
        return "accent_transition"
    if page_type == "thank_you":
        return "dark_resolution"
    if family == "process_system":
        return "dark_focus" if index % 3 == 0 else "light_blueprint"
    if family == "comparison_data":
        return "light_evidence"
    if family == "media":
        return "image_led"
    return "light_editorial" if index % 2 else "soft_contrast"


def build_surface_rhythm(deck: DeckBrief) -> List[Dict[str, Any]]:
    """Plan contrast rhythm without changing the selected deck palette."""
    pages = list(deck.page_briefs or [])
    out: List[Dict[str, Any]] = []
    prior = ""
    for index, page in enumerate(pages):
        mode = _mode(page, index)
        if mode == prior and mode not in {"light_evidence", "light_editorial"}:
            mode = "light_editorial"
        out.append({
            "page_id": str(page.page_id or "").strip(),
            "mode": mode,
            "palette_rule": (
                "use the deck's dark neutral as the dominant field with accent used selectively"
                if mode.startswith("dark")
                else "use a light neutral canvas with one substantial accent or dark contrast field"
            ),
            "continuity_rule": "preserve deck colors while changing massing and contrast from adjacent pages",
        })
        prior = mode
    return out


def surface_brief_for_page(deck: DeckBrief, page_id: str) -> Dict[str, Any]:
    target = str(page_id or "").strip()
    for item in build_surface_rhythm(deck):
        if item["page_id"] == target:
            return item
    return {}


__all__ = ["build_surface_rhythm", "surface_brief_for_page"]
