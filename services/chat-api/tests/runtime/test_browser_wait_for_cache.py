from app.enterprise_capabilities.browser.engine.wait_for_cache import (
    can_reuse_click_target,
    confirmed_click_target,
)
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


def _result(
    *,
    label="发送",
    ref="e2",
    resolution="action_rule",
    model_required=False,
    backend_node_id=None,
):
    return {
        "clickable_ref": ref,
        "resolution": resolution,
        "model_required": model_required,
        "observation": {
            "url": "https://mail.example/compose",
            "elements": [{
                "ref": ref,
                "role": "button",
                "name": label,
                "backendNodeId": backend_node_id,
            }],
        },
    }


def test_only_rule_confirmed_clickable_targets_are_cached():
    assert confirmed_click_target(_result()) is not None
    assert confirmed_click_target(_result(resolution="explicit_ref")) is None
    assert confirmed_click_target(_result(model_required=True)) is None


def test_cached_target_is_rejected_when_ref_label_changes_after_render():
    target = confirmed_click_target(_result())
    assert target is not None
    current = Observation(
        url="https://mail.example/compose",
        title="Mail",
        elements=[{"ref": "e2", "role": "menuitem", "name": "已发送"}],
    )
    assert not can_reuse_click_target(target, current)


def test_cached_target_is_reused_only_for_same_semantic_element():
    target = confirmed_click_target(_result())
    assert target is not None
    current = Observation(
        url="https://mail.example/compose",
        title="Mail",
        elements=[{"ref": "e2", "role": "button", "name": "发送"}],
    )
    assert can_reuse_click_target(target, current)


def test_cached_target_is_rejected_when_same_ref_and_label_belong_to_new_node():
    target = confirmed_click_target(_result(backend_node_id=101))
    assert target is not None
    current = Observation(
        url="https://mail.example/compose",
        title="Mail",
        elements=[{
            "ref": "e2",
            "role": "button",
            "name": "发送",
            "backendNodeId": 202,
        }],
    )

    assert not can_reuse_click_target(target, current)
