from app.enterprise_capabilities.browser.engine.agent_loop.planner import (
    _parse_decision,
    _recover_decision_from_contaminated_raw,
)


def test_bare_ref_is_not_recovered_as_click() -> None:
    assert _recover_decision_from_contaminated_raw('noise {"ref":"e7"} tail') is None


def test_explicit_hover_tool_survives_normal_parsing() -> None:
    decision = _parse_decision(
        '{"tool":"browser_hover","args":{"ref":"e7"},"rationale":"open submenu"}'
    )
    assert decision.tool == "browser_hover"
    assert decision.args == {"ref": "e7"}


def test_unambiguous_shapes_still_recover() -> None:
    scroll = _recover_decision_from_contaminated_raw(
        'noise {"direction":"down","ref":"menu"} tail'
    )
    assert scroll is not None
    assert scroll.tool == "browser_scroll"

    wait = _recover_decision_from_contaminated_raw(
        'noise {"text":"发布图文","timeout":1500} tail'
    )
    assert wait is not None
    assert wait.tool == "browser_wait_for"
