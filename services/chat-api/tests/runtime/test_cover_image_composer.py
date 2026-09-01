import asyncio

from app.services.presentation.contracts import (
    FreeformBlock,
    FreeformDeckBlueprint,
    FreeformPageBlueprint,
    FreeformTheme,
)
from app.services.presentation.cover_image_composer import CoverImageComposer


def _build_sample_blueprint() -> FreeformDeckBlueprint:
    cover_page = FreeformPageBlueprint(
        page_id="page_01",
        page_title="AI Native Presentation Engine",
        page_subtitle="Generate beautiful slides first, then recover editability",
        layout_type="cover",
        blocks=[
            FreeformBlock(
                id="cover_title",
                type="text_box",
                role="title",
                x=0.08,
                y=0.18,
                w=0.5,
                h=0.2,
                content="AI Native Presentation Engine",
                style={"font_size": 56},
            ),
            FreeformBlock(
                id="cover_subtitle",
                type="text_box",
                role="subtitle",
                x=0.08,
                y=0.45,
                w=0.45,
                h=0.1,
                content="Generate beautiful slides first, then recover editability",
                style={"font_size": 28},
            ),
            FreeformBlock(
                id="cover_tag",
                type="text_box",
                role="label",
                x=0.08,
                y=0.75,
                w=0.25,
                h=0.05,
                content="Proof of Concept / 2026",
                style={"font_size": 22},
            ),
        ],
    )
    metrics_page = FreeformPageBlueprint(
        page_id="page_02",
        page_title="Metrics",
        layout_type="content",
        blocks=[
            FreeformBlock(
                id="metrics_title",
                type="text_box",
                role="title",
                x=0.08,
                y=0.1,
                w=0.6,
                h=0.1,
                content="Metrics",
                style={"font_size": 40},
            )
        ],
    )
    return FreeformDeckBlueprint(
        deck_id="deck_001",
        deck_goal="Test Deck",
        target_audience="executive",
        theme=FreeformTheme(
            accent_color="#38bdf8",
            page_background="#0b1220",
            title_color="#ffffff",
            body_color="#cbd5e1",
            muted_color="#94a3b8",
            font_family="'PingFang SC', 'Microsoft YaHei', sans-serif",
        ),
        pages=[cover_page, metrics_page],
        runtime={
            "deck_brief": {
                "theme_factory_name": "tech-innovation",
                "visual_direction": ["tech", "executive", "clean hierarchy"],
                "design_tokens": {
                    "title_font_size": 58,
                    "subtitle_font_size": 30,
                    "body_font_size": 22,
                },
                "page_briefs": [
                    {"page_id": "page_01", "page_type": "cover"},
                    {"page_id": "page_02", "page_type": "content"},
                ],
            }
        },
    )


def test_cover_compose_success_rebuilds_only_cover(monkeypatch):
    composer = CoverImageComposer()
    blueprint = _build_sample_blueprint()
    original_page_2 = blueprint.pages[1].model_copy(deep=True)

    async def _fake_generate_cover_background(*, prompt: str, user_id: str):
        assert "LEFT 45%" in prompt
        assert user_id == "u_test"
        return "https://example.com/cover_bg.png"

    monkeypatch.setattr(composer, "_generate_cover_background", _fake_generate_cover_background)
    out = asyncio.run(composer.compose(blueprint=blueprint, user_id="u_test"))

    assert out is not blueprint
    assert len(out.pages) == 2
    cover = out.pages[0]
    assert cover.layout_type == "cover_programmatic_image_text"
    assert any(b.type == "image" and b.role == "background" for b in cover.blocks)
    assert any(b.role == "title" and "AI Native" in b.content for b in cover.blocks)
    assert any(b.role == "subtitle" and "Generate beautiful slides first" in b.content for b in cover.blocks)
    assert any(b.role == "label" and "Proof of Concept" in b.content for b in cover.blocks)

    # Non-cover pages stay unchanged.
    assert out.pages[1].model_dump() == original_page_2.model_dump()


def test_cover_compose_fallback_keeps_original_when_generation_fails(monkeypatch):
    composer = CoverImageComposer()
    blueprint = _build_sample_blueprint()
    original = blueprint.model_dump()

    async def _fake_generate_cover_background(*, prompt: str, user_id: str):
        return None

    monkeypatch.setattr(composer, "_generate_cover_background", _fake_generate_cover_background)
    out = asyncio.run(composer.compose(blueprint=blueprint, user_id="u_test"))

    assert out.model_dump() == original


def test_cover_compose_skips_when_title_missing(monkeypatch):
    composer = CoverImageComposer()
    blueprint = _build_sample_blueprint()
    # Remove all cover text and title metadata.
    blueprint.pages[0].blocks = []
    blueprint.pages[0].page_title = ""
    blueprint.pages[0].page_subtitle = ""
    original = blueprint.model_dump()

    async def _fake_generate_cover_background(*, prompt: str, user_id: str):
        raise AssertionError("should not attempt image generation when title is empty")

    monkeypatch.setattr(composer, "_generate_cover_background", _fake_generate_cover_background)
    out = asyncio.run(composer.compose(blueprint=blueprint, user_id="u_test"))

    assert out.model_dump() == original

