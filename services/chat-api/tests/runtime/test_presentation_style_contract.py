from app.services.presentation.contracts import FreeformDeckBlueprint
from app.services.presentation.html_renderer import HtmlRenderer
from app.services.presentation.pptx_compiler import PptxCompiler
from app.services.presentation.style_contract import PresentationStyleContract


def _mixed_style_deck() -> FreeformDeckBlueprint:
    return FreeformDeckBlueprint.model_validate({
        "deck_id": "style-contract",
        "theme": {"primary_color": "#2563eb", "page_style": {"backgroundColor": "#ffffff"}},
        "pages": [{
            "page_id": "page_01",
            "style": {"backgroundColor": "#f8fafc"},
            "blocks": [
                {
                    "id": "hero",
                    "type": "rectangle",
                    "x": 0.1, "y": 0.1, "w": 0.8, "h": 0.3,
                    "style": {
                        "backgroundColor": "#0f172a",
                        "borderRadius": 24,
                        "boxShadow": "soft",
                    },
                },
                {
                    "id": "title",
                    "type": "text_box",
                    "role": "headline",
                    "x": 0.15, "y": 0.15, "w": 0.6, "h": 0.1,
                    "content": "企业级智能体平台",
                    "style": {"fontSize": 44, "fontWeight": "bold", "textAlign": "left", "color": "#ffffff"},
                },
                {
                    "id": "rule",
                    "type": "line",
                    "x": 0.1, "y": 0.5, "x2": 0.9, "y2": 0.5,
                    "style": {"stroke": "#ff6600", "strokeWidth": 5},
                },
            ],
        }],
    })


def test_style_contract_converts_camel_case_and_svg_aliases() -> None:
    deck = PresentationStyleContract().canonicalize(_mixed_style_deck())
    page = deck.pages[0]
    hero, title, rule = page.blocks

    assert page.style["background"] == "#f8fafc"
    assert hero.style["background"] == "#0f172a"
    assert hero.style["border_radius"] == 24
    assert hero.style["box_shadow"] == "soft"
    assert title.style["font_size"] == 48
    assert title.style["font_weight"] == 700
    assert title.style["text_align"] == "left"
    assert rule.style["color"] == "#ff6600"
    assert rule.style["line_weight"] == 5
    assert deck.runtime["style_contract_version"] == PresentationStyleContract.VERSION


def test_style_contract_enforces_projection_readable_type_hierarchy() -> None:
    raw = _mixed_style_deck()
    raw.pages[0].blocks.extend([
        raw.pages[0].blocks[1].model_copy(update={
            "id": "section",
            "role": "section_label",
            "style": {"font_size": 14},
        }),
        raw.pages[0].blocks[1].model_copy(update={
            "id": "body",
            "role": "body",
            "style": {"font_size": 12},
        }),
    ])

    deck = PresentationStyleContract().canonicalize(raw)
    by_id = {block.id: block for block in deck.pages[0].blocks}

    assert by_id["title"].style["font_size"] >= 48
    assert by_id["section"].style["font_size"] >= 22
    assert by_id["body"].style["font_size"] >= 22
    assert by_id["body"].style["line_height"] >= 1.2


def test_style_contract_never_shrinks_below_semantic_floor() -> None:
    raw = _mixed_style_deck()
    raw.pages[0].blocks[1].role = "section_label"
    raw.pages[0].blocks[1].w = 0.06
    raw.pages[0].blocks[1].h = 0.02
    raw.pages[0].blocks[1].content = "很长的阶段标签不应被压缩成无法投影阅读的小字"
    raw.pages[0].blocks[1].style = {"font_size": 12}

    block = PresentationStyleContract().canonicalize(raw).pages[0].blocks[1]

    assert block.style["font_size"] >= 22


def test_style_contract_does_not_treat_every_value_role_as_a_metric() -> None:
    raw = _mixed_style_deck()
    raw.pages[0].blocks[1].role = "value_detail"
    raw.pages[0].blocks[1].style = {"font_size": 12}

    block = PresentationStyleContract().canonicalize(raw).pages[0].blocks[1]

    assert 22 <= block.style["font_size"] < 32


def test_html_renderer_uses_same_canonical_style_contract() -> None:
    result = HtmlRenderer().compile(blueprint=_mixed_style_deck())

    assert "background:#0f172a" in result.html
    assert "font-size:48px" in result.html or "font-size:48.0px" in result.html
    assert "font-weight:700" in result.html
    assert 'stroke="#ff6600"' in result.html


def test_html_renderer_draws_circle_content_and_line_opacity() -> None:
    deck = _mixed_style_deck()
    deck.pages[0].blocks.append(deck.pages[0].blocks[0].model_copy(update={
        "id": "numbered_node",
        "type": "circle",
        "content": "1",
        "style": {"background": "#0066ff", "color": "#ffffff"},
    }))
    deck.pages[0].blocks[2].style["opacity"] = 0.55

    result = HtmlRenderer().compile(blueprint=deck)

    assert 'id="numbered_node"' in result.html
    assert '>1</div>' in result.html
    assert 'opacity="0.55"' in result.html


def test_pptx_renderer_accepts_the_same_mixed_style_blueprint() -> None:
    payload = PptxCompiler().compile(_mixed_style_deck())

    assert payload.startswith(b"PK")
    assert len(payload) > 1000
