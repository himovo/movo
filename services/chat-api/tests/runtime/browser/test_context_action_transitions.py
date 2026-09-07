from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation
from app.enterprise_capabilities.browser.engine.context_action_transitions import context_action_transitions
from app.enterprise_capabilities.browser.engine.contexts.general import GeneralBrowserContext
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityTask


def test_completed_plan_is_exposed_as_atomic_context_transitions() -> None:
    before = Observation(
        url="https://www.baidu.com/",
        title="百度",
        revision="r1",
        elements=[{"ref": "search", "role": "searchbox", "editable": True}],
    )
    after = Observation(
        url="https://www.baidu.com/s?wd=MOVO",
        title="MOVO_百度搜索",
        revision="r2",
        elements=[
            {"ref": "r1", "role": "link", "href": "https://www.himovo.com/"},
            {"ref": "r2", "role": "link", "href": "https://example.com/"},
        ],
    )
    decision = Decision("browser_execute_plan", {
        "actions": [
            {"tool": "browser_fill", "args": {"ref": "search", "value": "MOVO"}},
            {"tool": "browser_press", "args": {"ref": "search", "key": "Enter"}},
        ],
    })
    transitions = context_action_transitions(
        decision,
        result={
            "status": "completed",
            "receipts": [
                {"index": 0, "tool": "browser_fill", "status": "completed"},
                {"index": 1, "tool": "browser_press", "status": "completed"},
            ],
            "observation": {},
        },
        ok=True,
        error=None,
        before=before,
        after=after,
    )
    assert [item.transition.decision.tool for item in transitions] == [
        "browser_fill", "browser_press",
    ]
    assert transitions[0].transition.target.role == "searchbox"

    context = GeneralBrowserContext(
        lang="zh",
        node=CapabilityTask(
            node_id="browser",
            goal="在百度搜索 MOVO 官网并打开结果",
            assigned_agent="agent.browser",
        ),
        goal="在百度搜索 MOVO 官网并打开结果",
        original_user_request="在百度搜索 MOVO 官网并打开结果",
    )
    for item in transitions:
        context.after_transition(item.transition, item.result, item.ok, error=item.error)
    assert "search" in context.completed


def test_same_route_ax_plan_confirms_search_without_hrefs() -> None:
    before = Observation(
        url="https://example.test/explore",
        title="Explore",
        revision="r1",
        elements=[
            {"ref": "search", "role": "searchbox", "editable": True, "value": ""},
            {"ref": "home", "role": "link", "backendNodeId": 10, "name": "Home"},
        ],
    )
    after = Observation(
        url=before.url,
        title=before.title,
        revision="r2",
        elements=[
            {
                "ref": "search-next", "role": "searchbox", "editable": True,
                "value": "DeepSeek Harness",
            },
            {"ref": "result-1", "role": "link", "backendNodeId": 20, "name": "Result one"},
            {"ref": "result-2", "role": "link", "backendNodeId": 21, "name": "Result two"},
        ],
    )
    decision = Decision("browser_execute_plan", {
        "actions": [
            {"tool": "browser_fill", "args": {"ref": "search", "value": "DeepSeek Harness"}},
            {"tool": "browser_press", "args": {"ref": "search", "key": "Enter"}},
        ],
    })
    context = GeneralBrowserContext(
        lang="en",
        node=CapabilityTask(
            node_id="browser",
            goal="Search DeepSeek Harness and open a result",
            assigned_agent="agent.browser",
        ),
        goal="Search DeepSeek Harness and open a result",
        original_user_request="Search DeepSeek Harness and open a result",
    )

    for item in context_action_transitions(
        decision,
        result={
            "status": "completed",
            "receipts": [
                {"index": 0, "tool": "browser_fill", "status": "completed"},
                {"index": 1, "tool": "browser_press", "status": "completed"},
            ],
        },
        ok=True,
        error=None,
        before=before,
        after=after,
    ):
        context.after_transition(item.transition, item.result, item.ok)

    assert "search" in context.completed


def test_stopped_plan_exposes_only_completed_actions() -> None:
    before = Observation(url="https://example.com", title="", elements=[])
    after = Observation(url="https://example.com", title="", elements=[])
    decision = Decision("browser_execute_plan", {
        "actions": [
            {"tool": "browser_scroll", "args": {"direction": "down"}},
            {"tool": "browser_click", "args": {"ref": "missing"}},
        ],
    })
    transitions = context_action_transitions(
        decision,
        result={
            "status": "stopped",
            "receipts": [
                {"index": 0, "tool": "browser_scroll", "status": "completed"},
                {"index": 1, "tool": "browser_click", "status": "failed"},
            ],
        },
        ok=False,
        error="action_failed",
        before=before,
        after=after,
    )
    assert [item.transition.decision.tool for item in transitions] == ["browser_scroll"]
