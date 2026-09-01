from app.enterprise_capabilities.browser.engine.effect_verification.completion_guard import assess_effect_completion
from app.enterprise_capabilities.browser.engine.effect_verification.decision_target import resolve_effect_target
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


def test_read_only_browser_done_does_not_require_side_effect_receipt():
    assert assess_effect_completion("browser.read", [], lang="zh").allowed is True


def test_publish_done_requires_confirmed_success_receipt():
    decision = assess_effect_completion("browser.publish", [], lang="zh")

    assert decision.allowed is False
    assert "不等于发布成功" in decision.reason


def test_publish_done_accepts_existing_effect_tracker_success():
    decision = assess_effect_completion(
        "browser.publish",
        [{"status": "confirmed_success", "action_name": "发送"}],
        lang="zh",
    )

    assert decision.allowed is True


def test_legacy_publish_alias_uses_the_same_completion_gate():
    assert assess_effect_completion("browser.publish_or_submit", [], lang="zh").allowed is False


def test_coordinate_click_resolves_to_nearest_observed_control():
    observation = Observation(
        url="https://example.test/post",
        title="Post",
        page_text="Send Cancel",
        elements=[
            {"ref": "e1", "role": "textbox", "x": 410, "y": 636, "visible": True},
            {"ref": "e2", "role": "button", "name": "Send", "x": 700, "y": 695, "visible": True},
        ],
    )

    target = resolve_effect_target(
        Decision(tool="browser_click_at", args={"x": 700, "y": 695}),
        observation,
    )

    assert target is not None
    assert target["ref"] == "e2"
