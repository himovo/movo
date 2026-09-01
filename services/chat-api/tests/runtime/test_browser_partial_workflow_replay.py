from __future__ import annotations

import asyncio

from app.enterprise_capabilities.browser.engine.drivers.base import BrowserDriver
from app.enterprise_capabilities.browser.engine.form_input.input_context import BrowserInputContext, InputCandidate
from app.enterprise_capabilities.browser.engine.workflow_cache.contracts import (
    CachedBrowserWorkflow,
    CachedCompletionContract,
    CachedParameterBinding,
    CachedWorkflowStep,
    WorkflowIdentity,
)
from app.enterprise_capabilities.browser.engine.workflow_cache.driver import LearnedWorkflowDriver
from app.enterprise_capabilities.browser.engine.workflow_cache.replay_plan import (
    build_replay_plan,
    normalize_semantic_replay_count,
)
from app.enterprise_capabilities.browser.engine.workflow_cache.semantic_inputs import SemanticInputValue
from app.enterprise_capabilities.browser.engine.workflow_cache.semantic_selector import (
    BrowserWorkflowRequirement,
    WorkflowSelectionResponse,
    WorkflowSemanticSelector,
)
from app.enterprise_capabilities.browser.engine.workflow_cache.service import BrowserWorkflowCacheService
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityTask
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


def _workflow() -> CachedBrowserWorkflow:
    return CachedBrowserWorkflow(
        workflow_id="article-draft",
        admission_revision=2,
        identity=WorkflowIdentity(
            user_id="u1",
            site_id="cms.example.test",
            operation_id="article.save_draft",
            capability_id="browser.submit",
            signature_hash="article-draft-signature",
        ),
        status="candidate",
        quality_score=90,
        dynamic_input_roles=["title", "body"],
        completion=CachedCompletionContract(capability_id="browser.submit"),
        steps=[
            CachedWorkflowStep(
                tool="browser_navigate",
                args={"url": "https://cms.example.test/editor"},
                source_url_shape="about:blank",
                target_url_shape="cms.example.test/editor",
            ),
            CachedWorkflowStep(
                tool="browser_fill",
                locator={"selector": "#title", "role": "textbox", "name": "标题"},
                arg_bindings={"value": CachedParameterBinding(
                    source="candidate", semantic_name="title", projection="plain_text",
                )},
                source_url_shape="cms.example.test/editor",
            ),
            CachedWorkflowStep(
                tool="browser_fill",
                locator={"selector": "#body", "role": "textbox", "name": "正文"},
                arg_bindings={"value": CachedParameterBinding(
                    source="candidate", semantic_name="body", projection="rich_html",
                )},
                source_url_shape="cms.example.test/editor",
            ),
            CachedWorkflowStep(
                tool="browser_click",
                locator={"selector": "#save", "role": "button", "name": "保存草稿"},
                source_url_shape="cms.example.test/editor",
            ),
        ],
    )


class _Repository:
    def __init__(self, workflow: CachedBrowserWorkflow) -> None:
        self.workflow = workflow

    async def find_candidates(self, **kwargs):
        return [self.workflow]

    async def find_user_candidates(self, **kwargs):
        return [self.workflow]

    async def find_by_id(self, workflow_id, *, include_quarantined=False):
        del include_quarantined
        return self.workflow if workflow_id == self.workflow.workflow_id else None


class _SelectionLLM:
    async def ainvoke_structured(self, messages, schema, **kwargs):
        assert schema is WorkflowSelectionResponse
        return WorkflowSelectionResponse(
            selected_workflow_id="article-draft",
            matching_workflow_ids=["article-draft"],
            confidence=0.98,
            reason="same article draft operation",
            parameter_values=[
                SemanticInputValue(role="title", value="本次标题"),
                SemanticInputValue(role="body", value="本次正文"),
            ],
            replay_step_count=3,
            missing_input_roles=["images"],
        )


class _ZeroPrefixSelectionLLM:
    def __init__(self) -> None:
        self.messages = []

    async def ainvoke_structured(self, messages, schema, **kwargs):
        self.messages = list(messages)
        assert schema is WorkflowSelectionResponse
        return WorkflowSelectionResponse(
            selected_workflow_id="article-draft",
            matching_workflow_ids=["article-draft"],
            confidence=0.97,
            reason="same complete browser save-draft operation",
            parameter_values=[
                SemanticInputValue(role="title", value="本次标题"),
                SemanticInputValue(role="body", value="本次正文"),
            ],
            replay_step_count=0,
            missing_input_roles=[],
            browser_requirements=[
                BrowserWorkflowRequirement(
                    kind="runtime_precondition",
                    description="等待用户完成登录",
                    category="authentication",
                ),
                BrowserWorkflowRequirement(
                    kind="completion_verification",
                    description="确认保存成功",
                ),
            ],
        )


class _Fallback(BrowserDriver):
    kind = "fallback"

    def __init__(self) -> None:
        self.calls = 0

    async def next_step(self, goal, history, observation, state_ledger=None):
        self.calls += 1
        return Decision(tool="browser_done", args={"summary": "explore missing image"})


def _context() -> BrowserInputContext:
    return BrowserInputContext(
        original_request="在内容平台创建文章，标题填本次标题，正文填本次正文，插入图片后保存草稿",
        candidates=[InputCandidate(
            candidate_id="image",
            source_kind="upstream",
            source_path="artifacts.image",
            semantic_name="images",
            value=["/tmp/current.png"],
            value_kind="file",
        )],
    )


def _observation(url: str) -> Observation:
    return Observation(
        url=url,
        title="editor",
        revision=url,
        state_fingerprint=url,
        elements=[
            {"ref": "title", "selector": "#title", "role": "textbox", "name": "标题"},
            {"ref": "body", "selector": "#body", "role": "textbox", "name": "正文"},
            {"ref": "save", "selector": "#save", "role": "button", "name": "保存草稿"},
        ],
    )


def test_same_business_workflow_gets_request_slots_before_compatibility_filter() -> None:
    workflow = _workflow()
    workflow = workflow.model_copy(update={
        "runtime_replay_step_count": 3,
        "runtime_missing_input_roles": ["images"],
    })
    context = _context()
    service = BrowserWorkflowCacheService(
        repository=_Repository(workflow),
        semantic_selector=WorkflowSemanticSelector(llm=_SelectionLLM()),
    )
    node = CapabilityTask(
        node_id="draft",
        goal="创建文章并保存草稿",
        assigned_agent="agent.browser",
        meta={
            "capability_id": "browser.submit",
            "browser_site_scope": "cms.example.test",
        },
    )

    matched = asyncio.run(service.lookup(
        user_id="u1", main_id="m1", node=node, input_context=context,
    ))

    assert matched is not None
    assert {item.semantic_name for item in context.candidates} == {"title", "body", "images"}
    assert matched.runtime_replay_step_count == 3
    assert matched.runtime_missing_input_roles == ["images"]


def test_upstream_preparation_does_not_turn_complete_browser_match_into_zero_replay() -> None:
    llm = _ZeroPrefixSelectionLLM()
    service = BrowserWorkflowCacheService(
        repository=_Repository(_workflow()),
        semantic_selector=WorkflowSemanticSelector(llm=llm),
    )
    context = BrowserInputContext(
        original_request=(
            "先下载图片，再到内容平台创建文章，标题填本次标题，"
            "正文填本次正文并保存草稿"
        ),
    )
    node = CapabilityTask(
        node_id="draft",
        goal="在内容平台创建文章并保存草稿",
        assigned_agent="agent.browser",
        meta={
            "capability_id": "browser.submit",
            "browser_site_scope": "cms.example.test",
        },
    )

    matched = asyncio.run(service.lookup(
        user_id="u1", main_id="m1", node=node, input_context=context,
    ))

    assert matched is not None
    assert matched.runtime_replay_step_count == -1
    assert matched.runtime_preconditions == [{
        "kind": "runtime_precondition",
        "description": "等待用户完成登录",
        "safe_cached_prefix_steps": -1,
        "category": "authentication",
    }]
    prompt = str(llm.messages[-1].content)
    assert '"browser_goal": "在内容平台创建文章并保存草稿"' in prompt
    assert '"user_request_for_parameter_extraction": "先下载图片' in prompt


def test_semantic_replay_boundary_rejects_useless_or_inconsistent_prefixes() -> None:
    assert normalize_semantic_replay_count(
        requested_count=0,
        total_steps=12,
        missing_input_roles=[],
        missing_replay_action_prefixes=[],
    ) == -1
    assert normalize_semantic_replay_count(
        requested_count=0,
        total_steps=12,
        missing_replay_action_prefixes=[0],
    ) is None
    assert normalize_semantic_replay_count(
        requested_count=-1,
        total_steps=12,
        missing_input_roles=["media"],
    ) is None
    assert normalize_semantic_replay_count(
        requested_count=5,
        total_steps=12,
        missing_replay_action_prefixes=[5],
    ) == 5
    assert normalize_semantic_replay_count(
        requested_count=2,
        total_steps=12,
        missing_replay_action_prefixes=[5],
    ) is None
    assert normalize_semantic_replay_count(
        requested_count=8,
        total_steps=12,
        missing_input_roles=["media"],
    ) == 8


def test_partial_replay_defers_terminal_action_and_hands_off_for_missing_input() -> None:
    workflow = _workflow().model_copy(update={
        "runtime_replay_step_count": 3,
        "runtime_missing_input_roles": ["images"],
    })
    context = _context()
    # These are normally added by semantic selection before driver creation.
    context.candidates.extend([
        InputCandidate("title", "request_semantic", "request_semantic.title", "title", "本次标题", plain_text="本次标题"),
        InputCandidate("body", "request_semantic", "request_semantic.body", "body", "本次正文", plain_text="本次正文"),
    ])
    plan = build_replay_plan(workflow, context)

    assert plan.mode == "partial"
    assert plan.missing_roles == ("images",)
    assert plan.terminal_deferred is True
    assert [step.tool for step in plan.steps] == [
        "browser_navigate", "browser_fill", "browser_fill",
    ]

    fallback = _Fallback()
    driver = LearnedWorkflowDriver(
        workflow=workflow,
        fallback=fallback,
        input_context=context,
    )
    blank = _observation("about:blank")
    editor = _observation("https://cms.example.test/editor")

    navigate = asyncio.run(driver.next_step("保存图文草稿", [], blank))
    assert navigate.tool == "browser_navigate"
    driver.on_step_completed(navigate, True, editor)
    title = asyncio.run(driver.next_step("保存图文草稿", [], editor))
    assert title.args["value"] == "本次标题"
    driver.on_step_completed(title, True, editor)
    body = asyncio.run(driver.next_step("保存图文草稿", [], editor))
    assert body.args["value"] == "本次正文"
    driver.on_step_completed(body, True, editor)
    handoff = asyncio.run(driver.next_step("保存图文草稿", [], editor))

    assert handoff.tool == "browser_done"
    assert fallback.calls == 1
    assert driver.replayed_any is True
    assert driver.replay_completed is False

    checkpoint = driver.export_checkpoint_state()
    resumed_fallback = _Fallback()
    resumed = LearnedWorkflowDriver(
        workflow=_workflow(),
        fallback=resumed_fallback,
        input_context=context,
    )
    resumed.restore_checkpoint_state(checkpoint)
    resumed_decision = asyncio.run(resumed.next_step("保存图文草稿", [], editor))
    assert resumed_decision.tool == "browser_done"
    assert resumed_fallback.calls == 1
    assert resumed.replay_completed is False


def test_replay_boundary_uses_semantic_count_not_control_text() -> None:
    workflow = _workflow().model_copy(update={
        "steps": [
            CachedWorkflowStep(tool="browser_click", locator={"role": "link", "name": "草稿箱"}),
            CachedWorkflowStep(tool="browser_click", locator={"role": "button", "name": "新的创作"}),
            CachedWorkflowStep(tool="browser_fill", locator={"role": "textbox", "name": "正文"}),
            CachedWorkflowStep(tool="browser_click", locator={"role": "button", "name": "保存为草稿"}),
        ],
        "runtime_replay_step_count": 3,
        "runtime_missing_input_roles": ["images"],
    })

    plan = build_replay_plan(workflow, _context())

    assert [step.locator.get("name") for step in plan.steps] == [
        "草稿箱", "新的创作", "正文",
    ]


def test_auth_precondition_pauses_without_degrading_and_resumes_same_workflow() -> None:
    failures: list[str] = []
    workflow = CachedBrowserWorkflow(
        workflow_id="auth-assisted-draft",
        identity=WorkflowIdentity(
            user_id="u1", site_id="cms.example.test",
            operation_id="article.save_draft", capability_id="browser.submit",
            signature_hash="auth-assisted-draft",
        ),
        runtime_preconditions=[{
            "kind": "runtime_precondition",
            "category": "authentication",
            "description": "complete authentication",
        }],
        steps=[
            CachedWorkflowStep(
                tool="browser_navigate", args={"url": "https://cms.example.test/"},
                source_url_shape="about:blank", target_url_shape="cms.example.test/",
            ),
            # Legacy recordings may still contain the human auth gesture.
            CachedWorkflowStep(
                tool="browser_click", locator={"role": "button", "name": "Quick access"},
                source_url_shape="cms.example.test/",
                target_url_shape="cms.example.test/home",
            ),
            CachedWorkflowStep(
                tool="browser_click", locator={"selector": "#menu", "role": "button"},
                source_url_shape="cms.example.test/home",
            ),
        ],
    )
    driver = LearnedWorkflowDriver(
        workflow=workflow,
        fallback=_Fallback(),
        input_context=BrowserInputContext(original_request="save a draft"),
        on_failure=failures.append,
    )
    blank = Observation(url="about:blank", title="", elements=[])
    blocked = Observation(
        url="https://cms.example.test/", title="Console", elements=[],
        auth={"state": "required", "confidence": 0.9},
    )

    navigate = asyncio.run(driver.next_step("save a draft", [], blank))
    assert navigate.tool == "browser_navigate"
    driver.on_step_completed(navigate, True, blocked)
    pause = asyncio.run(driver.next_step("save a draft", [], blocked))
    assert pause.tool == "browser_ask_user"
    assert pause.args["category"] == "login"
    assert failures == []
    assert driver.replay_failed is False

    checkpoint = driver.export_checkpoint_state()
    # Preferred-workflow resume does not run semantic matching again; the
    # request-scoped prerequisite must therefore survive in the checkpoint.
    resumed_workflow = workflow.model_copy(update={"runtime_preconditions": []})
    resumed = LearnedWorkflowDriver(
        workflow=resumed_workflow,
        fallback=_Fallback(),
        input_context=BrowserInputContext(original_request="save a draft"),
        on_failure=failures.append,
    )
    resumed.restore_checkpoint_state(checkpoint)
    resumed.apply_resume_signal({"human_outcome": "completed"})
    authenticated_home = Observation(
        url="https://cms.example.test/home", title="Home",
        auth={"state": "authenticated", "confidence": 0.9},
        elements=[{
            "ref": "menu", "selector": "#menu", "role": "button",
            "visible": True, "inViewport": True, "hitTestable": True,
        }],
    )
    next_action = asyncio.run(resumed.next_step("save a draft", [], authenticated_home))
    assert next_action.tool == "browser_click"
    assert next_action.args["ref"] == "menu"
    assert failures == []
    assert resumed.replay_failed is False
