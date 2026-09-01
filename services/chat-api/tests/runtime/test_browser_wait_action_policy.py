from app.enterprise_capabilities.browser.engine.wait_action_policy import should_resolve_wait_action
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision


def test_replay_probe_never_synthesizes_a_click() -> None:
    assert should_resolve_wait_action(
        Decision(
            tool="browser_wait_for",
            args={"text": "内容管理", "probe_only": True},
        ),
        ok=True,
        result={"matched": False, "model_required": True},
    ) is False


def test_existing_exploration_wait_keeps_action_resolution_behavior() -> None:
    assert should_resolve_wait_action(
        Decision(tool="browser_wait_for", args={"text": "内容管理"}),
        ok=True,
        result={"matched": True, "clickable_ref": "e9"},
    ) is True

