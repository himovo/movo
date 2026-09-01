from app.enterprise_capabilities.browser.engine.form_input.target_preflight import (
    is_stale_fill_target_error,
    validate_fill_target,
)
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


def _observation(elements):
    return Observation(
        url="https://example.test",
        title="test",
        elements=elements,
    )


def test_rejects_ref_that_now_points_to_navigation() -> None:
    observation = _observation([{
        "ref": "e2",
        "role": "link",
        "name": "首页",
        "editable": False,
        "visible": True,
    }])

    result = validate_fill_target(observation, {"ref": "e2", "value": "工单系统"})

    assert result.ok is False
    assert result.reason == "fill target is not editable"
    assert result.target is not None and result.target["name"] == "首页"


def test_accepts_editable_target_from_latest_observation() -> None:
    observation = _observation([{
        "ref": "e19",
        "role": "searchbox",
        "name": "Search",
        "editable": True,
        "visible": True,
    }])

    result = validate_fill_target(observation, {"ref": "e19", "value": "工单系统"})

    assert result.ok is True
    assert result.target is not None and result.target["role"] == "searchbox"


def test_rejects_missing_disabled_and_hidden_targets() -> None:
    missing = validate_fill_target(_observation([]), {"ref": "e1"})
    disabled = validate_fill_target(_observation([{
        "ref": "e1", "editable": True, "disabled": True, "visible": True,
    }]), {"ref": "e1"})
    hidden = validate_fill_target(_observation([{
        "ref": "e1", "editable": True, "disabled": False, "visible": False,
    }]), {"ref": "e1"})

    assert missing.ok is False
    assert disabled.ok is False
    assert hidden.ok is False


def test_stale_target_errors_are_not_business_fill_failures() -> None:
    assert is_stale_fill_target_error("target_not_editable: Fill target is not editable")
    assert is_stale_fill_target_error("target_not_found: Fill target no longer exists")
    assert is_stale_fill_target_error("target_not_found: Fill target disappeared after click")
    assert is_stale_fill_target_error("Unknown or stale element ref: e2")
    assert not is_stale_fill_target_error("value_not_applied: expected x, received y")
