from __future__ import annotations

import asyncio
from types import MethodType

from app.enterprise_capabilities.browser.engine import desktop_agent_executor as executor_module
from app.enterprise_capabilities.browser.engine.desktop_agent_executor import (
    DesktopAgentBrowserExecutor,
)
from app.enterprise_capabilities.runtime.execution_contracts import (
    CapabilityInputs,
    CapabilityTask,
)


class _CountingDriver:
    kind = "test"

    def __init__(self) -> None:
        self.calls = 0

    async def next_step(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("entry preflight must reject before model planning")

    def restore_checkpoint_state(self, payload):
        del payload


def test_blank_unresolved_entry_never_reaches_the_planner(monkeypatch) -> None:
    driver = _CountingDriver()
    monkeypatch.setattr(executor_module, "select_driver", lambda **kwargs: driver)
    monkeypatch.setattr(
        executor_module,
        "prepare_skill_fast_path",
        lambda **kwargs: None,
    )

    async def no_sites(user_id):
        del user_id
        return []

    monkeypatch.setattr(executor_module.site_profile_service, "list_for_user", no_sites)

    executor = DesktopAgentBrowserExecutor("user-1", "session-1")

    async def dispatch(self, decision):
        assert decision.tool == "browser_observe"
        return {
            "url": "about:blank",
            "title": "",
            "revision": "tab:blank",
            "elements": [],
            "pageText": "",
        }, True, None

    executor._dispatch = MethodType(dispatch, executor)
    node = CapabilityTask(
        node_id="browser",
        goal="打开某个网站并读取首页",
        assigned_agent="agent.browser",
    )
    inputs = CapabilityInputs(
        messages=[],
        raw_messages=[{"role": "user", "content": node.goal}],
        intent=node.goal,
        output_spec={"run_id": "run-entry-preflight"},
        language="zh",
    )

    async def collect():
        return [item async for item in executor.execute(node=node, inputs=inputs)]

    events = asyncio.run(collect())
    terminal = [item for item in events if item[0].get("type") == "subagent_done"][-1]

    assert driver.calls == 0
    assert terminal[0]["content"]["status"] == "failed_terminal"
    assert terminal[1]["browser_receipt"]["code"] == "entry_url_required"
    assert terminal[1]["browser_receipt"]["retryable"] is True
    assert terminal[1]["browser_result"]["data"]["required_argument"] == "target_url"
