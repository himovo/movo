from io import BytesIO
from zipfile import ZipFile

from PIL import Image

from app.services.presentation.contracts import FreeformDeckBlueprint, FreeformPageBlueprint, FreeformBlock
from app.services.presentation.cover_image_composer import CoverImageComposer
from app.services.presentation.image_layout import crop_image_bytes_to_aspect
from app.services.presentation.pptx_compiler import PptxCompiler
from app.services.presentation.style_contract import PresentationStyleContract
from app.services.presentation.text_box_style import parse_css_padding
from app.services.presentation.theme_factory_catalog import (
    apply_theme_spec_to_design_tokens,
    build_freeform_theme_from_design_tokens,
    get_theme_spec_by_slug,
)
from app.services.presentation.contracts import DesignTokens


def _deck() -> FreeformDeckBlueprint:
    return FreeformDeckBlueprint.model_validate({
        "deck_id": "render-contract",
        "theme": {
            "role_styles": {"body": {"color": "#334155", "font_family": "Microsoft YaHei"}},
        },
        "pages": [{
            "page_id": "page_01",
            "blocks": [{
                "id": "body",
                "type": "text_box",
                "role": "body",
                "x": 0.1,
                "y": 0.1,
                "w": 0.5,
                "h": 0.2,
                "content": "统一入口与统一治理",
                "style": {
                    "font_size": 22,
                    "padding": "8px 16px 12px 20px",
                    "vertical_align": "middle",
                },
            }],
        }],
    })


def test_role_styles_are_inherited_before_block_overrides() -> None:
    block = PresentationStyleContract().canonicalize(_deck()).pages[0].blocks[0]
    assert block.style["color"] == "#334155"
    assert block.style["font_family"] == "Microsoft YaHei"


def test_css_padding_parser_matches_browser_shorthand() -> None:
    assert parse_css_padding("8px") == (8, 8, 8, 8)
    assert parse_css_padding("8px 16px") == (8, 16, 8, 16)
    assert parse_css_padding("8px 16px 12px 20px") == (8, 16, 12, 20)


def test_pptx_writes_vertical_anchor_and_four_side_margins() -> None:
    payload = PptxCompiler().compile(_deck())
    with ZipFile(BytesIO(payload)) as archive:
        slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")
    assert 'anchor="ctr"' in slide_xml
    assert 'lIns="254000"' in slide_xml
    assert 'rIns="203200"' in slide_xml
    assert 'tIns="101600"' in slide_xml
    assert 'bIns="152400"' in slide_xml


def test_cover_background_injection_preserves_authored_blocks() -> None:
    page = FreeformPageBlueprint(
        page_id="cover",
        blocks=[FreeformBlock(id="authored-title", type="text_box", role="headline", content="MOVO")],
    )
    updated = CoverImageComposer()._inject_background_image(page, "https://example.com/cover.png")
    assert updated.blocks[0].role == "background"
    assert any(block.id == "authored-title" for block in updated.blocks)


def test_image_cover_crop_preserves_target_aspect_ratio() -> None:
    source = BytesIO()
    Image.new("RGB", (1200, 600), "#2563eb").save(source, format="JPEG")
    cropped = crop_image_bytes_to_aspect(source.getvalue(), target_width=400, target_height=400)
    with Image.open(BytesIO(cropped)) as result:
        assert result.width == result.height


def test_tech_theme_uses_a_canvas_surface_and_controlled_cyan() -> None:
    spec = get_theme_spec_by_slug("tech-innovation")
    tokens = apply_theme_spec_to_design_tokens(DesignTokens(), spec)
    theme = build_freeform_theme_from_design_tokens(tokens)
    assert theme.accent_color == "#22d3ee"
    assert theme.surface_style == {"background": "transparent"}
