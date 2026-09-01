from __future__ import annotations

import asyncio

from app.enterprise_capabilities.browser.engine.drivers.base import BrowserDriver
from app.enterprise_capabilities.browser.engine.drivers.factory import select_driver
from app.enterprise_capabilities.browser.engine.form_input.input_context import BrowserInputContext, InputCandidate
from app.enterprise_capabilities.browser.engine.form_input.contracts import FieldDescriptor
from app.enterprise_capabilities.browser.engine.workflow_cache.bindings import resolve_cached_bindings
from app.enterprise_capabilities.browser.engine.workflow_cache.contracts import (
    CachedBrowserWorkflow,
    CachedFieldBinding,
    CachedWorkflowStep,
)
from app.enterprise_capabilities.browser.engine.workflow_cache.distiller import (
    distill_field_bindings,
    distill_successful_prefix,
)
from app.enterprise_capabilities.browser.engine.workflow_cache.driver import LearnedWorkflowDriver
from app.enterprise_capabilities.browser.engine.workflow_cache.identity import build_workflow_identity
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityTask
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation, StepRecord


def _input_context(title: str, body: str, image: str) -> BrowserInputContext:
    return BrowserInputContext(
        original_request="发布文章",
        candidates=[
            InputCandidate(
                candidate_id="title",
                source_kind="upstream",
                source_path="artifacts.writer.publish_payload.title",
                semantic_name="title",
                value=title,
            ),
            InputCandidate(
                candidate_id="body",
                source_kind="upstream",
                source_path="artifacts.writer.publish_payload.body",
                semantic_name="body",
                value=body,
            ),
            InputCandidate(
                candidate_id="media",
                source_kind="upstream",
                source_path="artifacts.writer.publish_payload.media.0",
                semantic_name="media",
                value=[image],
                value_kind="file",
            ),
        ],
    )


def _publish_node(goal: str = "把文章发布到微信公众号") -> CapabilityTask:
    return CapabilityTask(
        node_id="publish",
        goal=goal,
        assigned_agent="agent.browser",
        meta={
            "capability_id": "browser.publish",
            "browser_site_scope": "mp.weixin.qq.com",
        },
    )


def _observation(url: str, revision: str, elements=None, text: str = "") -> Observation:
    return Observation(
        url=url,
        title="page",
        elements=list(elements or []),
        revision=revision,
        state_fingerprint=revision,
        page_text=text,
    )


def test_identity_ignores_business_values_and_wording() -> None:
    first = build_workflow_identity(
        user_id="u1",
        main_id="another-task",
        node=_publish_node("把文章发布到微信公众号"),
        input_context=_input_context("标题一", "正文一", "/tmp/one.png"),
    )
    second = build_workflow_identity(
        user_id="u1",
        main_id="m1",
        node=_publish_node("将新的图文发表到公众号"),
        input_context=_input_context("完全不同的标题", "新的正文", "/tmp/two.png"),
    )

    assert first is not None and second is not None
    assert first.site_id == "mp.weixin.qq.com"
    assert first.operation_id == "article.publish"
    assert first.signature_hash == second.signature_hash


def test_identity_separates_publish_from_save_draft() -> None:
    published = build_workflow_identity(
        user_id="u1",
        main_id="m1",
        node=_publish_node("正式发布公众号文章"),
        input_context=_input_context("标题", "正文", "/tmp/one.png"),
    )
    drafted = build_workflow_identity(
        user_id="u1",
        main_id="m1",
        node=_publish_node("保存到微信公众号草稿箱"),
        input_context=_input_context("标题", "正文", "/tmp/one.png"),
    )

    assert published is not None and drafted is not None
    assert published.operation_id == "article.publish"
    assert drafted.operation_id == "article.save_draft"
    assert published.signature_hash != drafted.signature_hash


def test_identity_uses_business_operation_not_internal_capability_variant() -> None:
    context = _input_context("标题", "正文", "/tmp/one.png")
    publish = _publish_node()
    compatible = _publish_node()
    compatible.meta["capability_id"] = "browser.publish_or_submit"

    first = build_workflow_identity(
        user_id="u1", main_id="task-a", node=publish, input_context=context,
    )
    second = build_workflow_identity(
        user_id="u1", main_id="task-b", node=compatible, input_context=context,
    )

    assert first is not None and second is not None
    assert first.operation_id == second.operation_id == "article.publish"
    assert first.signature_hash == second.signature_hash


def test_identity_uses_original_request_when_resumed_node_goal_omits_object_type() -> None:
    context = BrowserInputContext(
        original_request="在微信公众号创建一篇文章并保存到草稿箱",
        candidates=[InputCandidate(
            candidate_id="image", source_kind="upstream", source_path="payload.images",
            semantic_name="media", value=["/tmp/a.png"], value_kind="file",
        )],
    )
    node = CapabilityTask(
        node_id="resume",
        goal="填写标题和正文，然后保存为草稿",
        assigned_agent="agent.browser",
        meta={"capability_id": "browser.submit", "browser_site_scope": "mp.weixin.qq.com"},
    )

    identity = build_workflow_identity(
        user_id="u1", main_id="m1", node=node, input_context=context,
    )

    assert identity is not None
    assert identity.operation_id == "article.save_draft"


def test_distiller_stops_before_dynamic_values_and_files() -> None:
    blank = _observation("about:blank", "r0")
    home = _observation(
        "https://mp.weixin.qq.com/",
        "r1",
        [{"ref": "new-1", "role": "button", "name": "新建图文", "selector": "#new"}],
    )
    editor = _observation(
        "https://mp.weixin.qq.com/editor",
        "r2",
        [{"ref": "title-2", "role": "textbox", "name": "标题", "selector": "#title"}],
    )
    filled = _observation(
        editor.url,
        "r3",
        [{"ref": "title-3", "role": "textbox", "name": "标题", "value": "秘密标题"}],
    )
    history = [
        StepRecord(
            observation=home,
            decision_observation=blank,
            decision=Decision(tool="browser_navigate", args={"url": home.url}),
            ok=True,
        ),
        StepRecord(
            observation=editor,
            decision_observation=home,
            decision=Decision(tool="browser_click", args={"ref": "new-1"}),
            ok=True,
        ),
        StepRecord(
            observation=filled,
            decision_observation=editor,
            decision=Decision(tool="browser_fill", args={"ref": "title-2", "value": "秘密标题"}),
            ok=True,
        ),
    ]

    steps = distill_successful_prefix(history)

    assert [step.tool for step in steps] == ["browser_navigate", "browser_click"]
    assert steps[1].locator["name"] == "新建图文"
    assert "秘密标题" not in str([step.model_dump() for step in steps])


def test_field_binding_cache_keeps_semantics_but_not_business_value() -> None:
    editor = _observation(
        "https://mp.weixin.qq.com/editor",
        "r2",
        [{"ref": "title-2", "role": "textbox", "name": "标题", "selector": "#title"}],
    )
    filled = _observation(editor.url, "r3")
    context = _input_context("秘密标题", "正文", "/tmp/one.png")
    history = [StepRecord(
        observation=filled,
        decision_observation=editor,
        decision=Decision(tool="browser_fill", args={"ref": "title-2", "value": "秘密标题"}),
        ok=True,
    )]

    hints = distill_field_bindings(history, context)

    assert len(hints) == 1
    assert hints[0].semantic_name == "title"
    assert hints[0].locator["selector"] == "#title"
    assert "秘密标题" not in str(hints[0].model_dump())


def test_cached_field_binding_uses_current_run_value_and_changed_ref() -> None:
    hint = CachedFieldBinding(
        locator={"selector": "#title", "role": "textbox", "name": "标题"},
        semantic_name="title",
        source_path="artifacts.writer.publish_payload.title",
        action="fill",
    )
    current_context = _input_context("第二次的新标题", "新的正文", "/tmp/two.png")
    field = FieldDescriptor(
        field_key="current-title",
        ref="changed-ref",
        role="textbox",
        name="标题",
        control_kind="text",
        raw={"ref": "changed-ref", "selector": "#title", "role": "textbox", "name": "标题"},
    )

    bindings = resolve_cached_bindings([field], current_context, [hint])

    assert bindings["current-title"].value == "第二次的新标题"
    assert bindings["current-title"].candidate_id == "title"


class _Fallback(BrowserDriver):
    kind = "fallback"

    def __init__(self) -> None:
        self.calls = 0

    async def next_step(self, goal, history, observation, state_ledger=None):
        self.calls += 1
        return Decision(tool="browser_fill", args={"ref": "title-new", "value": "本次标题"})


def test_learned_driver_resolves_new_ref_then_hands_dynamic_form_to_fallback() -> None:
    identity = build_workflow_identity(
        user_id="u1",
        main_id="m1",
        node=_publish_node(),
        input_context=_input_context("标题", "正文", "/tmp/one.png"),
    )
    assert identity is not None
    workflow = CachedBrowserWorkflow(
        workflow_id="wf1",
        identity=identity,
        steps=[CachedWorkflowStep(
            tool="browser_click",
            locator={"role": "button", "name": "新建图文", "selector": "#new"},
        )],
    )
    fallback = _Fallback()
    driver = LearnedWorkflowDriver(workflow=workflow, fallback=fallback, input_context=_input_context(
        "标题", "正文", "/tmp/one.png",
    ))
    current = _observation(
        "https://mp.weixin.qq.com/",
        "r10",
        [{"ref": "changed-ref", "role": "button", "name": "新建图文", "selector": "#new"}],
    )

    first = asyncio.run(driver.next_step("发布", [], current))
    assert first.tool == "browser_click"
    assert first.args["ref"] == "changed-ref"
    assert first.args["__workflow_replay"] is True
    driver.on_step_completed(first, True, _observation("https://mp.weixin.qq.com/editor", "r11"))

    second = asyncio.run(driver.next_step("发布", [], current))
    assert second.tool == "browser_fill"
    assert second.args["value"] == "本次标题"
    assert "__workflow_replay" not in second.args
    assert fallback.calls == 1


def test_factory_prefers_explicit_skill_then_learned_workflow() -> None:
    context = _input_context("标题", "正文", "/tmp/one.png")
    identity = build_workflow_identity(
        user_id="u1", main_id="m1", node=_publish_node(), input_context=context,
    )
    assert identity is not None
    learned = CachedBrowserWorkflow(
        workflow_id="wf1",
        identity=identity,
        steps=[CachedWorkflowStep(tool="browser_navigate", args={"url": "https://mp.weixin.qq.com/"})],
    )

    selected = select_driver(
        lang="zh",
        enterprise_sites=None,
        output_spec={},
        input_context=context,
        capability_id="browser.publish",
        learned_workflow=learned,
    )
    assert selected.kind.startswith("learned_workflow")

    explicit = select_driver(
        lang="zh",
        enterprise_sites=None,
        output_spec={
            "selected_skill": {
                "skill_markdown": "---\nsteps:\n  - instruction: 打开后台\n    navigate_url: https://mp.weixin.qq.com/\n---",
            },
        },
        input_context=context,
        capability_id="browser.publish",
        learned_workflow=learned,
    )
    assert explicit.kind.startswith("skill_driven")
