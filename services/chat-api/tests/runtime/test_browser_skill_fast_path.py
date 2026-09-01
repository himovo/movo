import asyncio
from types import SimpleNamespace

from app.enterprise_capabilities.browser.engine.skill_fast_path import (
    execute_skill_fast_path,
    prepare_skill_fast_path,
    try_skill_fast_path,
)
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityTask


class FakeBridge:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def execute(self, tool, args, **kwargs):
        self.calls.append((tool, args, kwargs))
        return self.response


def test_browser_workflow_skill_uses_local_fast_path() -> None:
    bridge = FakeBridge({
        "ok": True,
        "result": {"status": "completed", "tier": "skill", "completed_actions": 4},
    })
    node = CapabilityTask(
        node_id="N_BROWSER",
        goal="保存到微信公众号草稿箱",
        assigned_agent="agent.browser",
        meta={
            "capability_id": "browser.submit",
            "workflow_step": {
                "node_type": "browser_automation",
                "instruction": "进入草稿箱，添加文章并保存草稿",
                "semantic_config": {
                    "targetName": "微信公众号后台",
                    "targetUrl": "https://mp.weixin.qq.com/",
                },
            },
        },
    )
    inputs = SimpleNamespace(output_spec={"graph_artifacts": {"N_WRITE": {"article_markdown": "正文"}}})

    result = asyncio.run(
        try_skill_fast_path(
            bridge=bridge,
            node=node,
            inputs=inputs,
            goal=node.goal,
        )
    )

    assert result is not None and result.completed
    assert result.artifacts("browser.submit")["confirmation"]["status"] == "completed"
    tool, args, kwargs = bridge.calls[0]
    assert tool == "browser_execute_workflow"
    assert args["target_name"] == "微信公众号后台"
    assert args["target_url"] == "https://mp.weixin.qq.com/"
    assert args["input_data"]["N_WRITE"]["article_markdown"] == "正文"
    assert kwargs["domain"] == "mp.weixin.qq.com"


def test_non_skill_browser_node_skips_fast_path() -> None:
    bridge = FakeBridge({"ok": True, "result": {"status": "completed"}})
    node = CapabilityTask(node_id="N_BROWSER", goal="浏览网页", assigned_agent="agent.browser")
    inputs = SimpleNamespace(output_spec={})

    result = asyncio.run(
        try_skill_fast_path(bridge=bridge, node=node, inputs=inputs, goal=node.goal)
    )

    assert result is None
    assert bridge.calls == []


def test_skill_fast_path_preparation_does_not_start_browser_work() -> None:
    bridge = FakeBridge({
        "ok": True,
        "result": {"status": "completed", "tier": "skill"},
    })
    node = CapabilityTask(
        node_id="N_BROWSER",
        goal="保存草稿",
        assigned_agent="agent.browser",
        meta={
            "workflow_step": {
                "node_type": "browser_automation",
                "instruction": "进入编辑器并保存草稿",
                "semantic_config": {"targetUrl": "https://mp.weixin.qq.com/"},
            },
        },
    )
    inputs = SimpleNamespace(output_spec={})

    request = prepare_skill_fast_path(node=node, inputs=inputs, goal=node.goal)

    assert request is not None
    assert bridge.calls == []
    result = asyncio.run(execute_skill_fast_path(bridge=bridge, request=request))
    assert result is not None and result.completed
    assert len(bridge.calls) == 1
