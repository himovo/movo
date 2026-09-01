from __future__ import annotations

from app.enterprise_capabilities.browser.engine.checkpoint import BrowserExecutionCheckpoint
from app.enterprise_capabilities.browser.engine.contexts.form import FormContext
from app.enterprise_capabilities.browser.engine.drivers.base import BrowserDriver
from app.enterprise_capabilities.browser.engine.drivers.skill import SkillDriver
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityTask
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation, StepRecord


class FallbackDriver(BrowserDriver):
    @property
    def kind(self) -> str:
        return "fallback"

    async def next_step(self, goal, history, observation, state_ledger=None):
        return Decision(tool="browser_done", args={})


def test_browser_checkpoint_restores_semantic_history_without_stale_refs():
    observation = Observation(url="https://mail.example/inbox", title="Inbox", elements=[])
    checkpoint = BrowserExecutionCheckpoint.capture(
        phase="waiting_auth",
        next_step=2,
        visible_tool_step=1,
        observation=observation,
        history=[StepRecord(
            observation=observation,
            decision=Decision(tool="browser_click", args={"ref": "e9", "domain": "mail.example"}),
            ok=True,
            result_digest="opened compose",
        )],
        authenticated_domains=set(),
        last_safe_url_by_domain={},
        login_recovery_failures={},
        wait_for_text_calls={},
        last_navigate_target="https://mail.example/inbox",
    )

    restored = checkpoint.restore_history()

    assert checkpoint.phase == "waiting_auth"
    assert restored[0].decision.tool == "browser_click"
    assert restored[0].decision.args == {"domain": "mail.example"}
    assert restored[0].observation.elements == []


def test_checkpoint_restores_executor_driver_and_context_state():
    observation = Observation(url="https://example.test/form", title="Form", elements=[])
    node = CapabilityTask(node_id="browser", goal="submit", assigned_agent="agent.browser")
    context = FormContext(lang="en", node=node, goal="submit", original_user_request="submit")
    context.phase = FormContext.PHASE_VERIFYING
    context.filled_fields = {"field-1"}
    context.step_counter = 4

    driver = SkillDriver(
        steps=[{"navigate_url": "https://example.test"}, {"navigate_url": "https://example.test/form"}],
        fallback=FallbackDriver(),
    )
    driver.restore_checkpoint_state({"index": 1, "unresolved_streak": 2, "handed_off": False})

    checkpoint = BrowserExecutionCheckpoint.capture(
        phase="waiting_auth",
        next_step=5,
        visible_tool_step=4,
        observation=observation,
        history=[],
        authenticated_domains={"example.test"},
        last_safe_url_by_domain={"example.test": observation.url},
        login_recovery_failures={"example.test": 1},
        wait_for_text_calls={"Submit": 1},
        wait_for_text_refs={"Submit": "button-1"},
        consecutive_failures=2,
        soft_recovery_used=True,
        no_progress_streak=2,
        last_progress_signature=(observation.url, 3, 7),
        driver_state=driver.export_checkpoint_state(),
        context_state=context.export_checkpoint_state(),
        browser_runtime_state={
            "business_actions": {"version": 1, "records": []},
            "form_transaction": {"version": 1, "fields": []},
        },
    )

    restored_driver = SkillDriver(
        steps=[{"navigate_url": "https://example.test"}, {"navigate_url": "https://example.test/form"}],
        fallback=FallbackDriver(),
    )
    restored_driver.restore_checkpoint_state(checkpoint.driver_state)
    restored_context = FormContext(lang="en", node=node, goal="submit", original_user_request="submit")
    restored_context.restore_checkpoint_state(checkpoint.context_state)

    assert restored_driver.steps_remaining == 1
    assert restored_context.phase == FormContext.PHASE_VERIFYING
    assert restored_context.filled_fields == {"field-1"}
    assert checkpoint.consecutive_failures == 2
    assert checkpoint.soft_recovery_used is True
    assert checkpoint.last_progress_signature == [observation.url, 3, 7]
    assert checkpoint.version == 3
    assert checkpoint.browser_runtime_state["business_actions"]["version"] == 1
