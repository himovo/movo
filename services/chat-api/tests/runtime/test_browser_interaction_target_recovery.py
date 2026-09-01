from app.enterprise_capabilities.browser.engine.interaction_target_recovery import (
    InteractionTargetRecovery,
    bind_coordinate_action,
    is_stale_interaction_target_error,
)
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


def test_classifies_live_click_target_failures_but_not_business_errors():
    assert is_stale_interaction_target_error("Click target moved or is covered: e89") is True
    assert is_stale_interaction_target_error("Click target is stale or no longer resolvable: e89") is True
    assert is_stale_interaction_target_error("Click target kept moving during pointer correction: e89") is True
    assert is_stale_interaction_target_error("Click target has no usable point: e89") is True
    assert is_stale_interaction_target_error("Click target resolves to a page container: e89") is True
    assert is_stale_interaction_target_error("permission denied") is False


def test_coordinate_typing_is_rebound_to_current_editable_ref():
    observation = Observation(
        url="https://example.test/post/1",
        title="Post",
        elements=[{
            "ref": "fresh-editor",
            "role": "textbox",
            "editable": True,
            "visible": True,
            "x": 640,
            "y": 708,
            "width": 100,
            "height": 44,
        }],
    )

    binding = bind_coordinate_action(
        Decision(tool="browser_type_at", args={"x": 683, "y": 728, "value": "评论内容"}),
        observation,
    )

    assert binding.decision.tool == "browser_fill"
    assert binding.decision.args == {"ref": "fresh-editor", "value": "评论内容"}


def test_coordinate_typing_is_blocked_when_current_dom_editors_do_not_match_point():
    observation = Observation(
        url="https://example.test/post/1",
        title="Post",
        elements=[{
            "ref": "current-editor",
            "role": "textbox",
            "editable": True,
            "visible": True,
            "x": 400,
            "y": 500,
            "width": 200,
            "height": 44,
        }],
    )

    binding = bind_coordinate_action(
        Decision(tool="browser_type_at", args={"x": 50, "y": 50, "value": "评论内容"}),
        observation,
    )

    assert binding.blocked is True
    assert binding.decision.tool == "browser_type_at"
    assert "最新字段 ref" in binding.reason


def test_coordinate_typing_keeps_visual_fallback_when_dom_has_no_editable_target():
    observation = Observation(
        url="https://example.test/canvas",
        title="Canvas editor",
        elements=[{"ref": "canvas", "role": "img", "visible": True}],
    )
    decision = Decision(tool="browser_type_at", args={"x": 50, "y": 50, "value": "文本"})

    binding = bind_coordinate_action(decision, observation)

    assert binding.blocked is False
    assert binding.decision == decision


def test_repeated_covered_target_is_quarantined_by_stable_identity():
    recovery = InteractionTargetRecovery(max_failures=2)
    first = Observation(
        url="https://example.test/post/1",
        title="Post",
        elements=[{
            "ref": "e1", "selector": "#editor", "role": "textbox",
            "editable": True, "visible": True,
        }],
    )
    decision = Decision(tool="browser_click", args={"ref": "e1"})
    recovery.record_failure(decision, first, "Click target moved or is covered: e1")
    recovery.record_failure(decision, first, "Click target moved or is covered: e1")
    refreshed = Observation(
        url=first.url,
        title=first.title,
        elements=[{
            "ref": "e19", "selector": "#editor", "role": "textbox",
            "editable": True, "visible": True,
        }],
    )

    blocker = recovery.blocker(
        Decision(tool="browser_click", args={"ref": "e19"}),
        refreshed,
    )

    assert blocker is not None
    assert "browser_fill" in blocker
