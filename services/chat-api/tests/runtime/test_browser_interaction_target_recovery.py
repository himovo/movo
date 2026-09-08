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
    assert is_stale_interaction_target_error("stale_target_rebind_missing: ax-0-41") is True
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


def test_quarantined_card_is_removed_from_planning_even_after_ref_replacement():
    recovery = InteractionTargetRecovery(max_failures=2)
    original = Observation(
        url="https://example.test/search?q=agent",
        title="Search",
        elements=[{
            "ref": "ax-old", "backendNodeId": 41, "role": "button",
            "scopeId": "results", "name": "Enterprise agent deployment guide",
            "visible": True,
        }],
    )
    decision = Decision(tool="browser_click", args={"ref": "ax-old"})
    recovery.record_failure(decision, original, "Click target moved or is covered: ax-old")
    recovery.record_failure(decision, original, "Click target moved or is covered: ax-old")

    refreshed = Observation(
        url=original.url,
        title=original.title,
        elements=[
            {
                "ref": "ax-new", "backendNodeId": 99, "role": "button",
                "scopeId": "results", "name": "Enterprise agent deployment guide",
                "visible": True,
            },
            {
                "ref": "ax-other", "backendNodeId": 100, "role": "link",
                "scopeId": "results", "name": "Another result", "visible": True,
            },
        ],
    )

    planning = recovery.planning_observation(refreshed)

    assert [item["ref"] for item in planning.elements] == ["ax-other"]
    assert recovery.quarantined_refs(refreshed) == ("ax-new",)
    assert len(refreshed.elements) == 2


def test_quarantined_editor_remains_visible_for_fill_recovery():
    recovery = InteractionTargetRecovery(max_failures=1)
    observation = Observation(
        url="https://example.test/form",
        title="Form",
        elements=[{
            "ref": "editor", "selector": "#editor", "role": "textbox",
            "editable": True, "visible": True,
        }],
    )
    recovery.record_failure(
        Decision(tool="browser_click", args={"ref": "editor"}),
        observation,
        "Click target moved or is covered: editor",
    )

    assert recovery.planning_observation(observation).elements == observation.elements


def test_shared_class_selector_does_not_quarantine_other_list_items():
    recovery = InteractionTargetRecovery(max_failures=1)
    original = Observation(
        url="https://example.test/search",
        title="Search",
        elements=[{
            "ref": "first", "selector": ".result-card", "role": "button",
            "scopeId": "results", "name": "First result", "visible": True,
        }],
    )
    recovery.record_failure(
        Decision(tool="browser_click", args={"ref": "first"}),
        original,
        "Click target moved or is covered: first",
    )
    refreshed = Observation(
        url=original.url,
        title=original.title,
        elements=[{
            "ref": "second", "selector": ".result-card", "role": "button",
            "scopeId": "results", "name": "Second result", "visible": True,
        }],
    )

    assert recovery.planning_observation(refreshed).elements == refreshed.elements
