import asyncio
import json
from pydantic import ValidationError

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation
from app.enterprise_capabilities.browser.engine.agent_loop.structured_output import (
    BrowserPlannerOutput,
    PlannedAction,
    decision_from_output,
)
from app.enterprise_capabilities.browser.engine.agent_loop.guidance import build_guidance
from app.enterprise_capabilities.browser.engine.agent_loop.turn_payload import build_turn_payload
from app.enterprise_capabilities.browser.engine.drivers import factory as driver_factory
from app.enterprise_capabilities.browser import service as browser_service
from app.enterprise_capabilities.browser.engine.agent_loop import planner as planner_module
from app.enterprise_capabilities.runtime.contracts import CapabilityExecutionContext


def test_driver_factory_selects_the_formal_exploration_driver(monkeypatch) -> None:
    class _Exploration:
        kind = "exploration"

        def __init__(self, **_kwargs):
            pass

    monkeypatch.setattr(driver_factory, "ExplorationDriver", _Exploration)
    selected = driver_factory.select_driver(
        lang="zh", enterprise_sites=None, output_spec={},
    )
    assert selected.kind == "exploration"


def test_browser_service_uses_the_formal_executor_without_a_mode_switch(monkeypatch) -> None:
    captured = {}

    class _Checkpoint:
        def __init__(self, **_kwargs):
            self.checkpoint = None
            self.subagent_id = "subagent-test"

        async def open(self):
            pass

        async def finish(self, _status):
            pass

    class _Executor:
        def __init__(self, _user_id, _session_id, **kwargs):
            captured.update(kwargs)

        async def execute(self, **_kwargs):
            yield {"type": "subagent_done", "content": {"status": "failed_terminal"}}, {}

    monkeypatch.setattr(browser_service.agent_registry, "get", lambda _user_id: object())
    monkeypatch.setattr(browser_service, "BrowserCheckpointSession", _Checkpoint)
    monkeypatch.setattr(browser_service, "DesktopAgentBrowserExecutor", _Executor)
    context = CapabilityExecutionContext(
        tenant_id="tenant", user_id="user", conversation_id="conversation",
        kernel_session_id="kernel", profile_version="profile", action_id="action",
        turn_context={},
    )
    asyncio.run(browser_service.browser_task({"objective": "read", "operation": "read"}, context))
    assert set(captured) == {"checkpoint_session"}
    assert "checkpoint_session" in captured


def test_search_actions_compile_to_revision_bound_plan() -> None:
    observation = _observation()
    output = BrowserPlannerOutput(
        kind="actions",
        summary="搜索 MOVO",
        actions=[
            PlannedAction(tool="browser_fill", args={"ref": "ax-0-42", "value": "MOVO"}),
            PlannedAction(tool="browser_press", args={"ref": "ax-0-42", "key": "Enter"}),
        ],
    )
    decision = decision_from_output(output, observation)
    assert decision.tool == "browser_execute_plan"
    assert decision.args["revision"] == "tab:ax:1"
    assert len(decision.args["actions"]) == 2


def test_planner_target_history_directive_survives_action_compilation() -> None:
    output = BrowserPlannerOutput.model_validate({
        "kind": "actions",
        "actions": [{"tool": "browser_click", "args": {"ref": "result"}}],
        "target_history": {
            "policy": "exclude_completed",
            "operation": "comment",
            "reason": "user requested an unprocessed target",
        },
    })
    observation = _observation()
    observation.elements.append({
        "ref": "result", "role": "link", "href": "https://example.test/posts/1",
    })

    decision = decision_from_output(output, observation)

    assert decision.commentary == {
        "target_history": {
            "policy": "exclude_completed",
            "operation": "comment",
            "reason": "user requested an unprocessed target",
        },
    }


def test_guidance_assigns_semantic_history_classification_to_existing_turn() -> None:
    guidance = build_guidance([], lang="zh")
    assert "policy=exclude_completed" in guidance
    assert "policy=allow_completed" in guidance
    assert "semantic classification, not keyword matching" in guidance


def test_singular_action_provider_shape_is_normalized() -> None:
    output = BrowserPlannerOutput.model_validate({
        "kind": "action",
        "action": {"tool": "browser_navigate", "args": {"url": "https://www.himovo.com"}},
        "summary": "打开首页",
    })
    decision = decision_from_output(output, _observation())
    assert decision.tool == "browser_navigate"
    assert decision.args == {"url": "https://www.himovo.com"}


def test_model_cannot_enable_internal_form_commit_recovery() -> None:
    output = BrowserPlannerOutput.model_validate({
        "kind": "actions",
        "actions": [{
            "tool": "browser_click",
            "args": {"ref": "ax-0-99", "__verified_form_commit": True},
        }],
        "summary": "提交",
    })

    decision = decision_from_output(output, _observation())

    assert decision.args == {"ref": "ax-0-99"}

    top_level = BrowserPlannerOutput.model_validate({
        "kind": "action",
        "tool": "browser_observe",
        "args": {},
    })
    assert decision_from_output(top_level, _observation()).tool == "browser_observe"


def test_done_preserves_capability_result_data() -> None:
    output = BrowserPlannerOutput(
        kind="done",
        summary="已读取首页",
        data={"result": {"title": "MOVO", "positioning": "企业智能体平台"}},
    )
    decision = decision_from_output(output, _observation())
    assert decision.tool == "browser_done"
    assert decision.args == {
        "summary": "已读取首页",
        "data": {
            "result": {
                "title": "MOVO",
                "positioning": "企业智能体平台",
            },
        },
    }


def test_commit_control_cannot_be_hidden_in_plan() -> None:
    observation = _observation(include_send=True)
    output = BrowserPlannerOutput(
        kind="actions",
        actions=[
            PlannedAction(tool="browser_fill", args={"ref": "ax-0-42", "value": "MOVO"}),
            PlannedAction(tool="browser_click", args={"ref": "send"}),
        ],
    )
    decision = decision_from_output(output, observation)
    assert decision.tool == "browser_fill"
    assert decision.args == {"ref": "ax-0-42", "value": "MOVO"}
    assert "decomposed" in decision.rationale


def test_unclassified_editable_search_candidate_is_filled_then_reobserved() -> None:
    observation = Observation(
        url="https://search.example.test",
        title="Search",
        revision="tab:ax:1",
        fresh=True,
        elements=[
            {
                "ref": "ax-0-11", "role": "textbox", "name": "动态热词",
                "selector": "#chat-textarea", "editable": True, "visible": True,
            },
            {
                "ref": "ax-0-46", "role": "button", "name": "执行查询",
                "editable": False, "visible": True,
            },
        ],
    )
    output = BrowserPlannerOutput(
        kind="actions",
        actions=[
            PlannedAction(tool="browser_fill", args={"ref": "ax-0-11", "value": "MOVO 官网"}),
            PlannedAction(tool="browser_click", args={"ref": "ax-0-46"}),
        ],
    )

    decision = decision_from_output(output, observation)

    assert decision.tool == "browser_fill"
    assert decision.args == {"ref": "ax-0-11", "value": "MOVO 官网"}
    assert "re-observation" in decision.rationale


def test_single_commit_action_stays_visible_to_legacy_safety_gate() -> None:
    observation = _observation(include_send=True)
    output = BrowserPlannerOutput(
        kind="actions",
        actions=[PlannedAction(tool="browser_click", args={"ref": "send"})],
    )
    decision = decision_from_output(output, observation)
    assert decision.tool == "browser_click"
    assert decision.args == {"ref": "send"}


def test_editor_activation_followed_by_observe_defers_observation() -> None:
    observation = Observation(
        url="https://example.test/article",
        title="Article",
        revision="tab:ax:1",
        fresh=True,
        elements=[{
            "ref": "comment-entry", "role": "button", "name": "说点什么...",
            "visible": True, "disabled": False, "editable": False,
        }],
    )
    output = BrowserPlannerOutput(
        kind="actions",
        actions=[
            PlannedAction(tool="browser_click", args={"ref": "comment-entry"}),
            PlannedAction(tool="browser_observe", args={}),
        ],
    )

    decision = decision_from_output(output, observation)

    assert decision.tool == "browser_click"
    assert decision.args == {"ref": "comment-entry"}
    assert "trailing_observation_deferred" in decision.rationale


def test_commit_click_followed_by_observe_stays_visible_to_outer_safety_gate() -> None:
    observation = _observation(include_send=True)
    output = BrowserPlannerOutput(
        kind="actions",
        actions=[
            PlannedAction(tool="browser_click", args={"ref": "send"}),
            PlannedAction(tool="browser_observe", args={}),
        ],
    )

    decision = decision_from_output(output, observation)

    assert decision.tool == "browser_click"
    assert decision.args == {"ref": "send"}
    assert "trailing_observation_deferred" in decision.rationale


def test_guidance_and_observation_are_capability_scoped_and_bounded() -> None:
    observation = _observation()
    observation.page_text = "x" * 20_000
    guidance = build_guidance(observation.elements, lang="zh")
    payload = build_turn_payload(
        "搜索 MOVO", [], observation,
        {"notes": ["ignored" * 10_000], "action_constraints": ["x" * 20_000]},
    )
    assert "SEARCH:" in guidance
    assert "SELECT:" not in guidance
    assert len(payload["observation"]["page_text"]) <= 2_500
    assert len(payload["state"]["action_constraints"][0]) == 1_000


def test_guidance_always_declares_exact_action_protocol_without_elements() -> None:
    guidance = build_guidance([], lang="zh")
    assert '"kind":"actions"' in guidance
    assert '"tool":"browser_observe"' in guidance
    assert "Every item in actions MUST contain tool and args" in guidance
    assert "Never use browser_type, browser_keypress" in guidance


def test_planner_module_emits_one_serial_search_segment(monkeypatch) -> None:
    captured = {}

    class _Client:
        async def ainvoke_structured(self, messages, schema, **_kwargs):
            captured["messages"] = messages
            return schema(
                kind="actions", summary="执行搜索",
                actions=[
                    {"tool": "browser_fill", "args": {"ref": "ax-0-42", "value": "MOVO"}},
                    {"tool": "browser_press", "args": {"ref": "ax-0-42", "key": "Enter"}},
                ],
            )

    monkeypatch.setattr(planner_module, "get_request_scoped_llm_client", lambda **_kwargs: _Client())
    planner = planner_module.Planner(lang="zh")
    decision = asyncio.run(planner.next_step("搜索 MOVO", [], _observation()))
    assert decision.tool == "browser_execute_plan"
    assert [item["tool"] for item in decision.args["actions"]] == ["browser_fill", "browser_press"]
    assert "SEARCH:" in str(captured["messages"][0].content)
    assert len(str(captured["messages"][1].content)) < 12_000


def test_planner_module_repairs_invalid_provider_action_shape_once(monkeypatch) -> None:
    calls = []

    class _Client:
        async def ainvoke_structured(self, messages, schema, **_kwargs):
            calls.append(messages)
            if len(calls) == 1:
                return schema.model_validate({
                    "kind": "actions",
                    "actions": [{"kind": "browser_keypress", "keys": ["ENTER"]}],
                })
            return schema.model_validate({
                "kind": "actions",
                "actions": [{"tool": "browser_observe", "args": {}}],
                "summary": "重新读取页面",
            })

    monkeypatch.setattr(planner_module, "get_request_scoped_llm_client", lambda **_kwargs: _Client())
    planner = planner_module.Planner(lang="zh")
    decision = asyncio.run(planner.next_step("搜索 MOVO", [], _observation()))
    assert decision.tool == "browser_observe"
    assert len(calls) == 2
    assert "browser_keypress" in str(calls[1][-1].content)


def test_planner_module_contract_failure_is_not_human_recovery(monkeypatch) -> None:
    class _Client:
        async def ainvoke_structured(self, _messages, schema, **_kwargs):
            return schema.model_validate({
                "kind": "actions",
                "actions": [{"kind": "browser_type", "text": "MOVO"}],
            })

    monkeypatch.setattr(planner_module, "get_request_scoped_llm_client", lambda **_kwargs: _Client())
    planner = planner_module.Planner(lang="zh")
    decision = asyncio.run(planner.next_step("搜索 MOVO", [], _observation()))
    assert decision.tool == "browser_fail"
    assert decision.args["error_code"] == "planner_contract_invalid"


def test_browser_prompt_remains_bounded_on_a_large_page() -> None:
    observation = _observation()
    observation.page_text = "正文" * 8_000
    observation.elements.extend([
        {
            "ref": f"e{index}", "role": "link", "name": (f"结果{index}" * 8),
            "text": (f"内容{index}" * 12), "href": f"https://example.test/{index}",
            "visible": True, "hitTestable": True, "inViewport": index < 20,
            "disabled": False,
        }
        for index in range(500)
    ])
    goal = "搜索 MOVO 并打开最相关的结果"
    payload = build_turn_payload(goal, [], observation, None)
    planner_chars = len(build_guidance(observation.elements, lang="zh")) + len(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )
    assert planner_chars < 15_000


def _observation(*, include_send: bool = False) -> Observation:
    elements = [{
        "ref": "ax-0-42", "role": "searchbox", "name": "搜索", "editable": True,
        "visible": True, "disabled": False,
    }]
    if include_send:
        elements.append({
            "ref": "send", "role": "button", "name": "发送", "semanticPurpose": "send",
            "visible": True, "disabled": False,
        })
    return Observation(
        url="https://example.test", title="Example", elements=elements,
        revision="tab:ax:1", fresh=True,
    )
