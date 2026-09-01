import asyncio

import pytest

from app.services.presentation.contracts import FreeformDeckBlueprint
from app.services.presentation.icon_library import resolve_icon_from_texts
from app.services.presentation.iconography_refiner import IconographyRefiner


def _deck() -> FreeformDeckBlueprint:
    return FreeformDeckBlueprint.model_validate({
        "deck_id": "icon-finish",
        "pages": [{
            "page_id": "page_01",
            "page_title": "企业智能化的挑战",
            "blocks": [{
                "id": "peer_group",
                "type": "group",
                "x": 0.1,
                "y": 0.2,
                "w": 0.8,
                "h": 0.6,
                "children": [
                    {"id": "security_icon", "type": "icon", "icon": "bulb", "coordinate_space": "parent", "x": 0.05, "y": 0.1, "w": 0.03, "h": 0.08},
                    {"id": "security_text", "type": "text_box", "coordinate_space": "parent", "x": 0.1, "y": 0.1, "w": 0.35, "h": 0.12, "content": "安全合规与审计", "style": {"font_size": 22}},
                    {"id": "growth_icon", "type": "icon", "icon": "bulb", "coordinate_space": "parent", "x": 0.52, "y": 0.1, "w": 0.06, "h": 0.12},
                    {"id": "growth_text", "type": "text_box", "coordinate_space": "parent", "x": 0.6, "y": 0.1, "w": 0.3, "h": 0.12, "content": "效率增长与业务成效", "style": {"font_size": 22}},
                ],
            }],
        }],
    })


def test_refiner_selects_semantic_icons_and_harmonizes_supporting_scale(monkeypatch) -> None:
    from app.services.presentation import iconography_refiner as module

    async def fake_choose_icons_with_llm(**kwargs):
        assert len(kwargs["items"]) == 2
        return ["shield-lock", "chart-line"]

    monkeypatch.setattr(module, "choose_icons_with_llm", fake_choose_icons_with_llm)
    result = asyncio.run(IconographyRefiner().refine(_deck()))
    children = result.pages[0].blocks[0].children
    security, growth = children[0], children[2]

    assert security.icon == "shield-lock"
    assert growth.icon == "chart-line"
    assert security.icon_svg and growth.icon_svg
    assert security.w == pytest.approx(growth.w)
    assert security.h == pytest.approx(growth.h)
    assert security.w * (1600 * 0.8) == pytest.approx(36.0)
    assert result.runtime["iconography_refiner"]["slot_count"] == 2


def test_chinese_icon_fallback_is_semantic() -> None:
    assert resolve_icon_from_texts("安全合规与审计", fallback="") == "shield-lock"
    assert resolve_icon_from_texts("知识库检索", fallback="") == "database"
