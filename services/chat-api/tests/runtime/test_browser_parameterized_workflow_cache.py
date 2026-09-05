from __future__ import annotations

import asyncio

from app.enterprise_capabilities.browser.engine.drivers.base import BrowserDriver
from app.enterprise_capabilities.browser.engine.form_input.input_context import BrowserInputContext, InputCandidate
from app.enterprise_capabilities.browser.engine.workflow_cache.compiler import compile_parameterized_workflow
from app.enterprise_capabilities.browser.engine.workflow_cache.contracts import (
    CachedBrowserWorkflow,
    CachedCompletionContract,
    CachedWorkflowStep,
    WorkflowIdentity,
)
from app.enterprise_capabilities.browser.engine.workflow_cache.driver import LearnedWorkflowDriver
from app.enterprise_capabilities.browser.engine.workflow_cache.parameters import resolve_request_slots
from app.enterprise_capabilities.browser.engine.workflow_cache.repository import BrowserWorkflowCacheRepository
from app.enterprise_capabilities.browser.engine.workflow_cache.service import BrowserWorkflowCacheService
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityTask
from app.enterprise_capabilities.browser.engine.workflow_cache.identity import build_workflow_identity
from app.enterprise_capabilities.browser.engine.workflow_cache.matching import request_fingerprint
from app.enterprise_capabilities.browser.engine.workflow_cache.semantic_selector import (
    SemanticWorkflowSelection,
    WorkflowSelectionResponse,
    WorkflowSemanticSelector,
)
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation, StepRecord


def _obs(url: str, revision: str, elements=None, text: str = "") -> Observation:
    return Observation(
        url=url,
        title="page",
        revision=revision,
        state_fingerprint=revision,
        elements=list(elements or []),
        page_text=text,
    )


def test_compiler_marks_auth_transition_as_runtime_precondition() -> None:
    before = Observation(
        url="https://console.example.test/", title="Console",
        auth={"state": "required", "confidence": 0.9},
        elements=[{
            "ref": "auth", "selector": "#auth", "role": "button",
            "name": "Continue", "visible": True,
        }],
    )
    after = Observation(
        url="https://console.example.test/home", title="Home",
        auth={"state": "authenticated", "confidence": 0.9}, elements=[],
    )
    compiled = compile_parameterized_workflow([
        StepRecord(
            decision_observation=before,
            observation=after,
            decision=Decision(tool="browser_click", args={"ref": "auth"}),
            ok=True,
        ),
    ], BrowserInputContext(original_request="open the console"))

    assert len(compiled.steps) == 1
    assert compiled.steps[0].execution_kind == "runtime_precondition"
    assert compiled.steps[0].precondition_category == "authentication"


def _record(before: Observation, after: Observation, tool: str, args: dict) -> StepRecord:
    return StepRecord(
        observation=after,
        decision_observation=before,
        decision=Decision(tool=tool, args=args),
        ok=True,
    )


def _workflow(compiled) -> CachedBrowserWorkflow:
    return CachedBrowserWorkflow(
        workflow_id="wf-parameterized",
        identity=WorkflowIdentity(
            user_id="u1",
            site_id="example.test",
            operation_id="catalog.search_and_open",
            capability_id="browser.search",
            signature_hash="sig",
        ),
        version=2,
        steps=compiled.steps,
        request_template=compiled.request_template,
    )


def test_compiler_binds_equivalent_repeated_recording_candidates() -> None:
    page = _obs("https://example.test/search", "empty", [
        {"ref": "q", "selector": "#search-input", "role": "textbox", "placeholder": "搜索"},
    ])
    filled = _obs(page.url, "filled")
    context = BrowserInputContext(
        original_request="搜索 Deepseek harness",
        candidates=[
            InputCandidate("first", "human_recording", "manual.search_query.1", "search_query", "Deepseek harness"),
            InputCandidate("hydrated", "human_recording", "manual.search_query.3", "search_query", "Deepseek harness"),
        ],
    )

    compiled = compile_parameterized_workflow([
        _record(page, filled, "browser_fill", {"ref": "q", "value": "Deepseek harness"}),
    ], context)

    assert compiled.complete is True
    assert compiled.skipped_actions == 0
    assert compiled.steps[0].arg_bindings["value"].semantic_name == "search_query"


class _Fallback(BrowserDriver):
    kind = "fallback"

    def __init__(self) -> None:
        self.calls = 0

    async def next_step(self, goal, history, observation, state_ledger=None):
        self.calls += 1
        return Decision(tool="browser_done", args={"summary": "fallback"})


def _complete(driver, decision: Decision, after: Observation) -> None:
    result = None
    if decision.tool == "browser_select":
        after.diagnostics = {
            **(after.diagnostics or {}),
            "select": {"confirmed": True},
        }
        result = {}
    elif decision.tool == "browser_scroll":
        after.diagnostics = {
            **(after.diagnostics or {}),
            "scroll": {"progressed": True},
        }
        result = {}
    elif decision.tool == "browser_wait_for":
        result = {"matched": True}
    driver.on_step_completed(decision, True, after, result)


def test_complete_search_and_dynamic_list_flow_replays_new_parameters() -> None:
    old_context = BrowserInputContext(original_request="在示例站搜索苹果手机并打开京东")
    blank = _obs("about:blank", "r0")
    search = _obs(
        "https://example.test/search", "r1",
        [{"ref": "q1", "role": "searchbox", "name": "搜索", "selector": "#q", "editable": True}],
    )
    filled = _obs(
        search.url, "r2",
        [{"ref": "q2", "role": "searchbox", "name": "搜索", "selector": "#q", "editable": True, "value": "苹果手机"}],
    )
    results = _obs(
        "https://example.test/search?q=%E8%8B%B9%E6%9E%9C", "r3",
        [{"ref": "old-result", "role": "link", "name": "京东", "text": "京东", "selector": "li:nth(1)"}],
    )
    detail = _obs("https://example.test/shop/12345", "r4", text="京东详情")
    history = [
        _record(blank, search, "browser_navigate", {"url": search.url}),
        _record(search, filled, "browser_fill", {"ref": "q1", "value": "苹果手机"}),
        _record(filled, results, "browser_press", {"ref": "q2", "key": "ENTER"}),
        _record(results, detail, "browser_click", {"ref": "old-result"}),
    ]

    compiled = compile_parameterized_workflow(history, old_context)

    assert [step.tool for step in compiled.steps] == [
        "browser_navigate", "browser_fill", "browser_press", "browser_click",
    ]
    assert resolve_request_slots(
        compiled.request_template, "在示例站搜索华为手机并打开淘宝",
    ) == ["华为手机", "淘宝"]
    serialized = str([step.model_dump() for step in compiled.steps])
    assert "苹果手机" not in serialized
    assert "京东" not in serialized

    current = BrowserInputContext(original_request="在示例站搜索华为手机并打开淘宝")
    fallback = _Fallback()
    failures: list[str] = []
    driver = LearnedWorkflowDriver(
        workflow=_workflow(compiled),
        fallback=fallback,
        input_context=current,
        on_failure=failures.append,
    )
    first = asyncio.run(driver.next_step("搜索并打开", [], blank))
    assert first.args["url"] == search.url
    new_search = _obs(search.url, "n1", [{"ref": "new-q", "role": "searchbox", "name": "搜索", "selector": "#q"}])
    _complete(driver, first, new_search)

    second = asyncio.run(driver.next_step("搜索并打开", [], new_search))
    assert second.tool == "browser_fill"
    assert second.args == {"ref": "new-q", "value": "华为手机"}
    new_filled = _obs(search.url, "n2", [{"ref": "new-q2", "role": "searchbox", "name": "搜索", "selector": "#q"}])
    _complete(driver, second, new_filled)

    third = asyncio.run(driver.next_step("搜索并打开", [], new_filled))
    assert third.tool == "browser_press" and third.args["key"] == "ENTER"
    new_results = _obs(
        "https://example.test/search?q=%E5%8D%8E%E4%B8%BA", "n3",
        [
            {"ref": "wrong", "role": "link", "name": "其他商店", "text": "其他商店", "selector": "li:nth(1)"},
            {"ref": "target", "role": "link", "name": "淘宝", "text": "淘宝", "selector": "li:nth(2)"},
        ],
    )
    _complete(driver, third, new_results)

    fourth = asyncio.run(driver.next_step("搜索并打开", [], new_results))
    assert fourth.tool == "browser_click"
    assert fourth.args["ref"] == "target"
    _complete(driver, fourth, _obs("https://example.test/shop/98765", "n4"))
    assert failures == []


def _publishing_context(title: str, body: str, html: str, category: str, image: str) -> BrowserInputContext:
    return BrowserInputContext(
        original_request="发布本次图文",
        candidates=[
            InputCandidate("title-id", "upstream", "payload.title", "title", title),
            InputCandidate("body-id", "upstream", "payload.body", "body", body, plain_text=body, rich_html=html),
            InputCandidate("category-id", "upstream", "payload.category", "category", category),
            InputCandidate("media-id", "upstream", "payload.media", "media", [image], value_kind="file"),
        ],
    )


def test_form_rich_text_select_upload_paste_and_submit_are_parameterized() -> None:
    old = _publishing_context("旧标题", "旧正文", "<p>旧正文</p>", "科技", "/tmp/old.png")
    editor = _obs("https://example.test/editor", "e0", [
        {"ref": "t0", "role": "textbox", "name": "标题", "selector": "#title"},
        {"ref": "b0", "role": "textbox", "name": "正文", "selector": "#body", "contentEditable": True},
        {"ref": "c0", "role": "listbox", "name": "分类", "selector": "#category"},
        {"ref": "f0", "role": "button", "name": "上传", "selector": "#file", "type": "file"},
        {"ref": "s0", "role": "button", "name": "发布", "selector": "#submit"},
    ])
    history = [
        _record(editor, _obs(editor.url, "e1"), "browser_fill", {"ref": "t0", "value": "旧标题"}),
        _record(editor, _obs(editor.url, "e2"), "browser_fill", {
            "ref": "b0", "value": "旧正文", "rich_html": "<p>旧正文</p>",
        }),
        _record(editor, _obs(editor.url, "e3"), "browser_select", {"ref": "c0", "value": "科技"}),
        _record(editor, _obs(editor.url, "e4"), "browser_upload_file", {"ref": "f0", "sources": ["/tmp/old.png"]}),
        _record(editor, _obs(editor.url, "e5"), "browser_paste_image", {"editor_ref": "b0", "sources": ["/tmp/old.png"]}),
        _record(editor, _obs("https://example.test/published/12345", "e6"), "browser_click", {"ref": "s0"}),
    ]

    compiled = compile_parameterized_workflow(history, old)

    assert [step.tool for step in compiled.steps] == [
        "browser_fill", "browser_fill", "browser_select", "browser_upload_file",
        "browser_paste_image", "browser_click",
    ]
    serialized = str([step.model_dump() for step in compiled.steps])
    for secret in ("旧标题", "旧正文", "<p>旧正文</p>", "科技", "/tmp/old.png"):
        assert secret not in serialized

    new = _publishing_context("新标题", "新正文", "<h2>新正文</h2>", "财经", "/tmp/new.png")
    live_editor = _obs(editor.url, "x0", [
        {"ref": "t1", "role": "textbox", "name": "标题", "selector": "#title"},
        {"ref": "b1", "role": "textbox", "name": "正文", "selector": "#body", "contentEditable": True},
        {"ref": "c1", "role": "listbox", "name": "分类", "selector": "#category"},
        {"ref": "f1", "role": "button", "name": "上传", "selector": "#file", "type": "file"},
        {"ref": "s1", "role": "button", "name": "发布", "selector": "#submit"},
    ])
    driver = LearnedWorkflowDriver(
        workflow=_workflow(compiled), fallback=_Fallback(), input_context=new,
    )
    decisions = []
    for index in range(6):
        decision = asyncio.run(driver.next_step("发布", [], live_editor))
        decisions.append(decision)
        after = _obs(
            "https://example.test/published/98765" if index == 5 else editor.url,
            f"x{index + 1}",
            live_editor.elements,
        )
        _complete(driver, decision, after)
        live_editor = after

    assert decisions[0].args["value"] == "新标题"
    assert decisions[1].args["value"] == "新正文"
    assert decisions[1].args["rich_html"] == "<h2>新正文</h2>"
    assert decisions[2].args["value"] == "财经"
    assert decisions[3].args["sources"] == ["/tmp/new.png"]
    assert decisions[4].tool == "browser_paste_image"
    assert decisions[4].args["editor_ref"] == "b1"
    assert decisions[5].args["ref"] == "s1"


def test_plain_form_values_can_be_rebound_directly_from_request_slots() -> None:
    old = BrowserInputContext(original_request="填写姓名张三，城市北京")
    form = _obs("https://example.test/form", "f0", [
        {"ref": "name-old", "role": "textbox", "name": "姓名", "selector": "#name"},
        {"ref": "city-old", "role": "textbox", "name": "城市", "selector": "#city"},
    ])
    compiled = compile_parameterized_workflow([
        _record(form, _obs(form.url, "f1"), "browser_fill", {"ref": "name-old", "value": "张三"}),
        _record(form, _obs(form.url, "f2"), "browser_fill", {"ref": "city-old", "value": "北京"}),
    ], old)
    live = _obs(form.url, "n0", [
        {"ref": "name-new", "role": "textbox", "name": "姓名", "selector": "#name"},
        {"ref": "city-new", "role": "textbox", "name": "城市", "selector": "#city"},
    ])
    driver = LearnedWorkflowDriver(
        workflow=_workflow(compiled), fallback=_Fallback(),
        input_context=BrowserInputContext(original_request="填写姓名李四，城市上海"),
    )

    name_decision = asyncio.run(driver.next_step("填表", [], live))
    _complete(driver, name_decision, _obs(form.url, "n1", live.elements))
    city_decision = asyncio.run(driver.next_step("填表", [], live))

    assert name_decision.args == {"ref": "name-new", "value": "李四"}
    assert city_decision.args == {"ref": "city-new", "value": "上海"}


def test_successful_cached_navigation_finishes_locally_without_fallback() -> None:
    context = BrowserInputContext(original_request="打开示例站首页")
    start = _obs("about:blank", "a")
    landed = _obs("https://example.test/", "b", text="首页")
    compiled = compile_parameterized_workflow([
        _record(start, landed, "browser_navigate", {"url": landed.url}),
    ], context)
    workflow = _workflow(compiled).model_copy(update={
        "completion": CachedCompletionContract(capability_id="browser.navigate"),
    })
    fallback = _Fallback()
    driver = LearnedWorkflowDriver(
        workflow=workflow, fallback=fallback, input_context=context,
    )

    navigate = asyncio.run(driver.next_step("打开首页", [], start))
    _complete(driver, navigate, landed)
    done = asyncio.run(driver.next_step("打开首页", [], landed))

    assert done.tool == "browser_done"
    assert done.args["data"]["final_url"] == landed.url
    assert fallback.calls == 0


def test_rejected_local_completion_switches_to_llm_fallback() -> None:
    context = BrowserInputContext(original_request="读取示例数据")
    compiled = type("Compiled", (), {"steps": [], "request_template": None})()
    workflow = _workflow(compiled).model_copy(update={
        "completion": CachedCompletionContract(capability_id="browser.read"),
        "request_fingerprint": "fingerprint",
    })
    fallback = _Fallback()
    failures: list[str] = []
    driver = LearnedWorkflowDriver(
        workflow=workflow, fallback=fallback, input_context=context,
        on_failure=failures.append,
    )
    page = _obs("https://example.test/data", "a", text="库存 42")

    local_done = asyncio.run(driver.next_step("读取", [], page))
    fallback_done = asyncio.run(driver.next_step("读取", [], page))

    assert local_done.tool == "browser_done"
    assert local_done.args["data"]["result"]["text"] == "库存 42"
    assert fallback_done.tool == "browser_done"
    assert fallback.calls == 1
    assert len(failures) == 1


def test_unknown_browser_operation_still_gets_cache_identity() -> None:
    node = CapabilityTask(
        node_id="unknown",
        goal="在示例系统完成未分类操作",
        assigned_agent="agent.browser",
        meta={"capability_id": "browser.automation", "browser_site_scope": "example.test"},
    )

    identity = build_workflow_identity(
        user_id="u1", main_id="task", node=node,
        input_context=BrowserInputContext(original_request=node.goal),
    )

    assert identity is not None
    assert identity.operation_id.startswith("unknown.")


def test_page_precondition_mismatch_fails_closed_and_reports_once() -> None:
    context = BrowserInputContext(original_request="打开详情")
    start = _obs("https://example.test/list", "a", [
        {"ref": "open", "role": "button", "name": "打开", "selector": "#open"},
    ])
    compiled = compile_parameterized_workflow([
        _record(start, _obs("https://example.test/detail", "b"), "browser_click", {"ref": "open"}),
    ], context)
    failures: list[str] = []
    fallback = _Fallback()
    driver = LearnedWorkflowDriver(
        workflow=_workflow(compiled), fallback=fallback, input_context=context,
        on_failure=failures.append,
    )

    decision = asyncio.run(driver.next_step("打开详情", [], _obs("https://example.test/settings", "x")))

    assert decision.tool == "browser_done"
    assert fallback.calls == 1
    assert len(failures) == 1


def test_page_postcondition_mismatch_stops_replay() -> None:
    context = BrowserInputContext(original_request="打开详情")
    start = _obs("https://example.test/list", "a", [
        {"ref": "open", "role": "button", "name": "打开", "selector": "#open"},
    ])
    compiled = compile_parameterized_workflow([
        _record(start, _obs("https://example.test/detail", "b"), "browser_click", {"ref": "open"}),
    ], context)
    failures: list[str] = []
    fallback = _Fallback()
    driver = LearnedWorkflowDriver(
        workflow=_workflow(compiled), fallback=fallback, input_context=context,
        on_failure=failures.append,
    )
    decision = asyncio.run(driver.next_step("打开详情", [], start))

    driver.on_step_completed(decision, True, _obs("https://example.test/list", "c"))
    refresh = asyncio.run(driver.next_step("打开详情", [], start))
    assert refresh.tool == "browser_observe"
    driver.on_step_completed(refresh, True, start)
    retry = asyncio.run(driver.next_step("打开详情", [], start))
    assert retry.tool == "browser_click"
    driver.on_step_completed(retry, True, start)
    next_decision = asyncio.run(driver.next_step("打开详情", [], start))

    assert next_decision.tool == "browser_done"
    assert fallback.calls == 1
    assert len(failures) == 1


def test_async_popup_replay_waits_for_successor_before_falling_back() -> None:
    context = BrowserInputContext(original_request="打开内容管理中的草稿箱")
    home = _obs("https://example.test/home", "a", [
        {"ref": "content", "role": "menuitem", "name": "内容管理", "selector": "li:nth-of-type(3)"},
    ])
    workflow = CachedBrowserWorkflow(
        workflow_id="wf-popup",
        identity=WorkflowIdentity(
            user_id="u1", site_id="example.test", operation_id="draft.open",
            capability_id="browser.navigate", signature_hash="sig-popup",
        ),
        steps=[
            CachedWorkflowStep(
                tool="browser_click",
                locator={"role": "menuitem", "name": "内容管理", "selector": "li:nth-of-type(3)"},
                source_url_shape="example.test/home",
                target_url_shape="example.test/home",
                expect_state_change=True,
            ),
            CachedWorkflowStep(
                tool="browser_click",
                locator={"role": "link", "name": "草稿箱", "selector": "#draft"},
                source_url_shape="example.test/home",
                target_url_shape="example.test/drafts",
                expect_state_change=True,
            ),
        ],
    )
    fallback = _Fallback()
    failures: list[str] = []
    driver = LearnedWorkflowDriver(
        workflow=workflow, fallback=fallback, input_context=context,
        on_failure=failures.append,
    )

    click = asyncio.run(driver.next_step("打开草稿箱", [], home))
    driver.on_step_completed(click, False, home)
    wait = asyncio.run(driver.next_step("打开草稿箱", [], home))

    assert wait.tool == "browser_wait_for"
    assert wait.args["text"] == "草稿箱"
    menu_open = _obs(home.url, "b", [
        *home.elements,
        {"ref": "draft-live", "role": "link", "name": "草稿箱", "selector": "#draft"},
    ])
    driver.on_step_completed(wait, True, menu_open, {"matched": True})
    open_draft = asyncio.run(driver.next_step("打开草稿箱", [], menu_open))

    assert open_draft.tool == "browser_click"
    assert open_draft.args["ref"] == "draft-live"
    assert fallback.calls == 0
    assert failures == []


def test_terminal_cached_click_gets_observation_grace_but_is_never_retried() -> None:
    context = BrowserInputContext(original_request="保存草稿")
    editor = _obs("https://example.test/editor", "a", [
        {"ref": "save", "role": "button", "name": "保存草稿", "selector": "#save"},
    ])
    workflow = CachedBrowserWorkflow(
        workflow_id="wf-save",
        identity=WorkflowIdentity(
            user_id="u1", site_id="example.test", operation_id="article.save_draft",
            capability_id="browser.submit", signature_hash="sig-save",
        ),
        steps=[CachedWorkflowStep(
            tool="browser_click",
            locator={"role": "button", "name": "保存草稿", "selector": "#save"},
            source_url_shape="example.test/editor",
            target_url_shape="example.test/editor",
            expect_state_change=True,
        )],
    )
    fallback = _Fallback()
    failures: list[str] = []
    driver = LearnedWorkflowDriver(
        workflow=workflow, fallback=fallback, input_context=context,
        on_failure=failures.append,
    )

    click = asyncio.run(driver.next_step("保存", [], editor))
    driver.on_step_completed(click, False, editor)
    observe = asyncio.run(driver.next_step("保存", [], editor))
    assert observe.tool == "browser_observe"
    driver.on_step_completed(observe, True, editor)
    fallback_done = asyncio.run(driver.next_step("保存", [], editor))

    assert fallback_done.tool == "browser_done"
    assert fallback.calls == 1
    assert len(failures) == 1
    assert "index=0" in failures[0]


def test_dynamic_direct_navigation_url_is_rebound_from_current_request() -> None:
    old_url = "https://example.test/items/12345"
    new_url = "https://example.test/items/98765"
    context = BrowserInputContext(original_request=f"打开 {old_url}")
    compiled = compile_parameterized_workflow([
        _record(_obs("about:blank", "a"), _obs(old_url, "b"), "browser_navigate", {"url": old_url}),
    ], context)
    driver = LearnedWorkflowDriver(
        workflow=_workflow(compiled), fallback=_Fallback(),
        input_context=BrowserInputContext(original_request=f"打开 {new_url}"),
    )

    decision = asyncio.run(driver.next_step("打开", [], _obs("about:blank", "x")))

    assert decision.args["url"] == new_url


def test_direct_search_url_query_is_parameterized_without_storing_old_query() -> None:
    old_url = "https://example.test/search?q=%E8%8B%B9%E6%9E%9C%E6%89%8B%E6%9C%BA&sort=hot"
    context = BrowserInputContext(original_request="搜索苹果手机并查看热门结果")
    compiled = compile_parameterized_workflow([
        _record(_obs("about:blank", "a"), _obs(old_url, "b"), "browser_navigate", {"url": old_url}),
    ], context)
    driver = LearnedWorkflowDriver(
        workflow=_workflow(compiled), fallback=_Fallback(),
        input_context=BrowserInputContext(original_request="搜索华为手机并查看热门结果"),
    )

    decision = asyncio.run(driver.next_step("搜索", [], _obs("about:blank", "x")))

    assert decision.args["url"] == "https://example.test/search?q=%E5%8D%8E%E4%B8%BA%E6%89%8B%E6%9C%BA&sort=hot"
    assert "苹果手机" not in str(compiled.steps[0].model_dump())


def test_changed_request_shape_falls_back_before_any_cached_navigation() -> None:
    old_context = BrowserInputContext(original_request="在示例站搜索苹果手机")
    search = _obs("https://example.test/search", "a", [
        {"ref": "q", "role": "searchbox", "name": "搜索", "selector": "#q"},
    ])
    compiled = compile_parameterized_workflow([
        _record(_obs("about:blank", "z"), search, "browser_navigate", {"url": search.url}),
        _record(search, _obs(search.url, "b"), "browser_fill", {"ref": "q", "value": "苹果手机"}),
    ], old_context)
    fallback = _Fallback()
    failures: list[str] = []
    driver = LearnedWorkflowDriver(
        workflow=_workflow(compiled), fallback=fallback,
        input_context=BrowserInputContext(original_request="请查一下华为手机的资料"),
        on_failure=failures.append,
    )

    decision = asyncio.run(driver.next_step("搜索", [], _obs("about:blank", "x")))

    assert decision.tool == "browser_done"
    assert fallback.calls == 1
    assert len(failures) == 1


class _RecordingRepository:
    def __init__(self) -> None:
        self.saved = []
        self.failures = []

    async def upsert_success(self, **kwargs):
        self.saved.append(kwargs)
        return _workflow(type("Compiled", (), {
            "steps": kwargs["steps"],
            "request_template": kwargs["request_template"],
        })())

    async def mark_failure(self, workflow_id, reason):
        self.failures.append((workflow_id, reason))


class _LookupRepository:
    def __init__(self, candidates) -> None:
        self.candidates = list(candidates)
        self.candidate_queries = []

    async def find(self, identity):
        return None

    async def find_candidates(self, **kwargs):
        self.candidate_queries.append(kwargs)
        return list(self.candidates)

    async def find_user_candidates(self, **kwargs):
        self.candidate_queries.append({"all_sites": True, **kwargs})
        return list(self.candidates)

    async def find_by_id(self, workflow_id, *, include_quarantined=False):
        del include_quarantined
        return next((item for item in self.candidates if item.workflow_id == workflow_id), None)


class _ChoosingSelector:
    def __init__(self, workflow_id: str = "", *, fail: bool = False) -> None:
        self.workflow_id = workflow_id
        self.fail = fail
        self.calls = []

    async def select(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("semantic model unavailable")
        workflow = next(
            (item for item in kwargs["candidates"] if item.workflow_id == self.workflow_id),
            None,
        )
        if workflow is None:
            return None
        return SemanticWorkflowSelection(workflow=workflow, confidence=0.93, reason="same operation")


class _StructuredSelectionLLM:
    def __init__(self, response: WorkflowSelectionResponse) -> None:
        self.response = response
        self.messages = []

    async def ainvoke_structured(self, messages, schema, **kwargs):
        self.messages = list(messages)
        assert schema is WorkflowSelectionResponse
        return self.response


def test_navigation_only_success_is_cached_without_input_candidates() -> None:
    repository = _RecordingRepository()
    service = BrowserWorkflowCacheService(repository=repository)
    context = BrowserInputContext(original_request="打开示例站首页")
    history = [_record(
        _obs("about:blank", "a"),
        _obs("https://example.test/", "b"),
        "browser_navigate",
        {"url": "https://example.test/"},
    )]
    node = CapabilityTask(
        node_id="nav",
        goal="打开示例站首页",
        assigned_agent="agent.browser",
        meta={"capability_id": "browser.navigate", "browser_site_scope": "example.test"},
    )

    async def run_capture():
        service.schedule_success_capture(
            user_id="u1", main_id="task", node=node, input_context=context,
            history=history, run_id="run", replayed=False,
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    asyncio.run(run_capture())

    assert len(repository.saved) == 1
    assert repository.saved[0]["steps"][0].tool == "browser_navigate"


def test_success_capture_recovers_missing_site_from_successful_trace() -> None:
    repository = _RecordingRepository()
    service = BrowserWorkflowCacheService(repository=repository)
    context = BrowserInputContext(original_request="打开目标系统首页")
    history = [_record(
        _obs("about:blank", "a"),
        _obs("https://portal.example.internal/home", "b"),
        "browser_navigate",
        {"url": "https://portal.example.internal/home"},
    )]
    node = CapabilityTask(
        node_id="nav", goal="打开目标系统首页", assigned_agent="agent.browser",
        meta={"capability_id": "browser.navigate"},
    )

    async def run_capture():
        service.schedule_success_capture(
            user_id="u1", main_id="task", node=node, input_context=context,
            history=history, run_id="run", replayed=False,
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    asyncio.run(run_capture())

    assert len(repository.saved) == 1
    assert repository.saved[0]["identity"].site_id == "portal.example.internal"


def test_unknown_task_matches_site_candidate_locally_with_new_parameter() -> None:
    old_context = BrowserInputContext(original_request="处理客户张三")
    page = _obs("https://example.test/customers", "a", [
        {"ref": "search", "role": "searchbox", "name": "客户", "selector": "#customer"},
    ])
    compiled = compile_parameterized_workflow([
        _record(page, _obs(page.url, "b"), "browser_fill", {"ref": "search", "value": "张三"}),
    ], old_context)
    cached = _workflow(compiled).model_copy(update={
        "identity": WorkflowIdentity(
            user_id="u1", site_id="example.test", operation_id="unknown.old",
            capability_id="browser.automation", signature_hash="old-signature",
        ),
        "request_fingerprint": "old",
        "completion": CachedCompletionContract(capability_id="browser.automation"),
    })
    service = BrowserWorkflowCacheService(
        repository=_LookupRepository([cached]),
        semantic_selector=_ChoosingSelector(cached.workflow_id),
    )
    node = CapabilityTask(
        node_id="unknown",
        goal="处理客户李四",
        assigned_agent="agent.browser",
        meta={"capability_id": "browser.automation", "browser_site_scope": "example.test"},
    )

    matched = asyncio.run(service.lookup(
        user_id="u1", main_id="new-task", node=node,
        input_context=BrowserInputContext(original_request="处理客户李四"),
    ))

    assert matched is not None
    assert matched.workflow_id == cached.workflow_id


def test_missing_site_scope_uses_bounded_semantic_cross_site_fallback() -> None:
    request = "请到内容运营平台创建文章并保存草稿"
    cached = CachedBrowserWorkflow(
        workflow_id="content-platform-draft",
        identity=WorkflowIdentity(
            user_id="u1", site_id="cms.example.internal",
            operation_id="article.save_draft", capability_id="browser.submit",
            signature_hash="cms-draft-signature",
        ),
        version=3,
        steps=[CachedWorkflowStep(
            tool="browser_click",
            locator={"role": "button", "name": "保存草稿", "selector": "#save"},
        )],
        request_fingerprint=request_fingerprint(request),
        completion=CachedCompletionContract(capability_id="browser.submit"),
    )
    repository = _LookupRepository([cached])
    selector = _ChoosingSelector(cached.workflow_id)
    service = BrowserWorkflowCacheService(
        repository=repository,
        semantic_selector=selector,
    )
    node = CapabilityTask(
        node_id="save", goal="创建文章并保存草稿", assigned_agent="agent.browser",
        meta={"capability_id": "browser.publish_or_submit"},
    )

    matched = asyncio.run(service.lookup(
        user_id="u1", main_id="m", node=node,
        input_context=BrowserInputContext(original_request=request),
    ))

    assert matched is not None
    assert matched.workflow_id == cached.workflow_id
    assert repository.candidate_queries == [{"all_sites": True, "user_id": "u1"}]
    assert selector.calls[0]["site_id"] == ""


def test_resume_keeps_checkpoint_workflow_across_operation_label_drift() -> None:
    request = "在微信公众号创建一篇文章并保存到草稿箱"
    cached = CachedBrowserWorkflow(
        workflow_id="wf-original",
        identity=WorkflowIdentity(
            user_id="u1", site_id="mp.weixin.qq.com",
            operation_id="article.save_draft", capability_id="browser.submit",
            signature_hash="article-signature",
        ),
        version=3,
        steps=[CachedWorkflowStep(
            tool="browser_click",
            locator={"role": "button", "name": "保存草稿", "selector": "#save"},
        )],
        request_fingerprint=request_fingerprint(request),
        completion=CachedCompletionContract(capability_id="browser.submit"),
    )
    service = BrowserWorkflowCacheService(repository=_LookupRepository([cached]))
    resumed_node = CapabilityTask(
        node_id="resume",
        goal="填写内容并保存",
        assigned_agent="agent.browser",
        meta={"capability_id": "browser.submit", "browser_site_scope": "mp.weixin.qq.com"},
    )

    matched = asyncio.run(service.lookup(
        user_id="u1", main_id="m2", node=resumed_node,
        input_context=BrowserInputContext(original_request=request),
        preferred_workflow_id="wf-original",
    ))

    assert matched is not None
    assert matched.workflow_id == "wf-original"


def test_site_wide_ranking_prefers_repaired_candidate_over_degraded_exact_label() -> None:
    request = "保存本次文章草稿"
    base = {
        "identity": WorkflowIdentity(
            user_id="u1", site_id="example.test", operation_id="article.save_draft",
            capability_id="browser.submit", signature_hash="exact-signature",
        ),
        "version": 3,
        "steps": [CachedWorkflowStep(
            tool="browser_click",
            locator={"role": "button", "name": "保存草稿", "selector": "#save"},
        )],
        "request_fingerprint": request_fingerprint(request),
        "completion": CachedCompletionContract(capability_id="browser.submit"),
        "quality_score": 80,
    }
    degraded = CachedBrowserWorkflow(
        workflow_id="old", status="degraded", failure_count=1, **base,
    )
    repaired = CachedBrowserWorkflow(
        workflow_id="repaired", status="candidate",
        identity=base["identity"].model_copy(update={
            "operation_id": "resource.save_draft", "signature_hash": "drifted-signature",
        }),
        version=base["version"], steps=base["steps"],
        request_fingerprint=base["request_fingerprint"], completion=base["completion"],
        quality_score=base["quality_score"], supersedes_workflow_id="old",
    )
    service = BrowserWorkflowCacheService(
        repository=_LookupRepository([degraded, repaired]),
        semantic_selector=_ChoosingSelector(repaired.workflow_id),
    )
    node = CapabilityTask(
        node_id="save", goal=request, assigned_agent="agent.browser",
        meta={"capability_id": "browser.submit", "browser_site_scope": "example.test"},
    )

    matched = asyncio.run(service.lookup(
        user_id="u1", main_id="m", node=node,
        input_context=BrowserInputContext(original_request=request),
    ))

    assert matched is not None
    assert matched.workflow_id == "repaired"


def test_semantic_selector_chooses_across_planner_capability_drift() -> None:
    request = "在微信公众号创建文章并保存到草稿箱"
    cached = CachedBrowserWorkflow(
        workflow_id="wechat-save-draft",
        identity=WorkflowIdentity(
            user_id="u1", site_id="mp.weixin.qq.com",
            operation_id="article.save_draft", capability_id="browser.submit",
            signature_hash="save-draft-signature",
        ),
        version=3,
        steps=[CachedWorkflowStep(
            tool="browser_click",
            locator={"role": "button", "name": "保存为草稿"},
        )],
        request_fingerprint=request_fingerprint(request),
        completion=CachedCompletionContract(capability_id="browser.submit"),
        quality_score=80,
    )
    repository = _LookupRepository([cached])
    selector = _ChoosingSelector(cached.workflow_id)
    service = BrowserWorkflowCacheService(
        repository=repository,
        semantic_selector=selector,
    )
    # The product name was resolved by the planner into site_context; the user
    # did not need to include a literal URL in the request.
    node = CapabilityTask(
        node_id="save", goal=request, assigned_agent="agent.browser",
        meta={
            "capability_id": "browser.publish_or_submit",
            "site_context": {"entry_url": "https://mp.weixin.qq.com/"},
        },
    )

    matched = asyncio.run(service.lookup(
        user_id="u1", main_id="m", node=node,
        input_context=BrowserInputContext(original_request=request),
    ))

    assert matched is cached
    assert repository.candidate_queries == [{"user_id": "u1", "site_id": "mp.weixin.qq.com"}]
    assert selector.calls[0]["site_id"] == "mp.weixin.qq.com"
    assert selector.calls[0]["current_capability_id"] == "browser.publish_or_submit"


def test_semantic_no_match_does_not_force_local_cache_replay() -> None:
    request = "删除这篇文章"
    cached = CachedBrowserWorkflow(
        workflow_id="publish-only",
        identity=WorkflowIdentity(
            user_id="u1", site_id="example.test", operation_id="article.publish",
            capability_id="browser.publish", signature_hash="publish-signature",
        ),
        steps=[CachedWorkflowStep(
            tool="browser_click", locator={"role": "button", "name": "发布"},
        )],
        request_fingerprint=request_fingerprint(request),
        completion=CachedCompletionContract(capability_id="browser.publish"),
    )
    service = BrowserWorkflowCacheService(
        repository=_LookupRepository([cached]),
        semantic_selector=_ChoosingSelector(),
    )
    node = CapabilityTask(
        node_id="delete", goal=request, assigned_agent="agent.browser",
        meta={"capability_id": "browser.delete", "browser_site_scope": "example.test"},
    )

    matched = asyncio.run(service.lookup(
        user_id="u1", main_id="m", node=node,
        input_context=BrowserInputContext(original_request=request),
    ))

    assert matched is None


def test_semantic_selector_failure_falls_back_without_capability_hard_rejection() -> None:
    request = "保存文章草稿"
    cached = CachedBrowserWorkflow(
        workflow_id="local-fallback",
        identity=WorkflowIdentity(
            user_id="u1", site_id="example.test", operation_id="article.save_draft",
            capability_id="browser.submit", signature_hash="save-signature",
        ),
        steps=[CachedWorkflowStep(
            tool="browser_click", locator={"role": "button", "name": "保存草稿"},
        )],
        request_fingerprint=request_fingerprint(request),
        completion=CachedCompletionContract(capability_id="browser.submit"),
    )
    service = BrowserWorkflowCacheService(
        repository=_LookupRepository([cached]),
        semantic_selector=_ChoosingSelector(fail=True),
    )
    node = CapabilityTask(
        node_id="save", goal=request, assigned_agent="agent.browser",
        meta={"capability_id": "browser.publish_or_submit", "browser_site_scope": "example.test"},
    )

    matched = asyncio.run(service.lookup(
        user_id="u1", main_id="m", node=node,
        input_context=BrowserInputContext(original_request=request),
    ))

    assert matched is cached


def test_semantic_selector_prompt_contains_resolved_site_and_value_free_route_summary() -> None:
    request = "在微信公众号保存一篇新文章草稿"
    cached = CachedBrowserWorkflow(
        workflow_id="wf-safe-summary",
        identity=WorkflowIdentity(
            user_id="u1", site_id="mp.weixin.qq.com", operation_id="article.save_draft",
            capability_id="browser.submit", signature_hash="safe-summary",
        ),
        steps=[CachedWorkflowStep(
            tool="browser_fill",
            locator={"role": "textbox", "name": "标题"},
            arg_bindings={},
        ), CachedWorkflowStep(
            tool="browser_click", locator={"role": "button", "name": "保存为草稿"},
        )],
        request_fingerprint=request_fingerprint(request),
        completion=CachedCompletionContract(capability_id="browser.submit"),
        dynamic_input_roles=["title", "body", "images"],
    )
    llm = _StructuredSelectionLLM(WorkflowSelectionResponse(
        selected_workflow_id=cached.workflow_id,
        confidence=0.91,
        reason="same site and save-draft outcome",
    ))
    selector = WorkflowSemanticSelector(llm=llm)

    selection = asyncio.run(selector.select(
        site_id="mp.weixin.qq.com",
        context=BrowserInputContext(original_request=request),
        current_operation_id="article.save_draft",
        current_capability_id="browser.publish_or_submit",
        candidates=[cached],
    ))

    assert selection is not None and selection.workflow is cached
    prompt = str(llm.messages[-1].content)
    assert '"resolved_site": "mp.weixin.qq.com"' in prompt
    assert '"workflow_id": "wf-safe-summary"' in prompt
    assert '"name": "保存为草稿"' in prompt


def test_semantic_selector_does_not_reject_explicit_match_on_uncalibrated_confidence() -> None:
    request = "在微信公众号创建文章、粘贴图片并保存为草稿"
    cached = CachedBrowserWorkflow(
        workflow_id="wf-low-confidence",
        identity=WorkflowIdentity(
            user_id="u1", site_id="mp.weixin.qq.com",
            operation_id="article.save_draft", capability_id="browser.submit",
            signature_hash="low-confidence",
        ),
        steps=[CachedWorkflowStep(
            tool="browser_click", locator={"role": "button", "name": "保存为草稿"},
        )],
        request_fingerprint=request_fingerprint(request),
        completion=CachedCompletionContract(capability_id="browser.submit"),
    )
    llm = _StructuredSelectionLLM(WorkflowSelectionResponse(
        selected_workflow_id=cached.workflow_id,
        matching_workflow_ids=[cached.workflow_id],
        confidence=0.68,
        reason="same save-draft operation",
    ))

    selection = asyncio.run(WorkflowSemanticSelector(llm=llm).select(
        site_id="mp.weixin.qq.com",
        context=BrowserInputContext(original_request=request),
        current_operation_id="article.save_draft",
        current_capability_id="browser.submit",
        candidates=[cached],
    ))

    assert selection is not None
    assert selection.workflow is cached
    assert selection.confidence == 0.68


def test_semantic_group_is_ranked_locally_by_route_health() -> None:
    request = "在微信公众号创建文章并保存为草稿"
    identity = WorkflowIdentity(
        user_id="u1", site_id="mp.weixin.qq.com",
        operation_id="article.save_draft", capability_id="browser.submit",
        signature_hash="same-operation",
    )
    degraded = CachedBrowserWorkflow(
        workflow_id="semantic-anchor", identity=identity, status="degraded",
        quality_score=80, consecutive_failures=1,
        request_fingerprint=request_fingerprint(request),
        steps=[CachedWorkflowStep(
            tool="browser_click", locator={"role": "button", "name": "保存为草稿"},
        )],
        completion=CachedCompletionContract(capability_id="browser.submit"),
    )
    healthy = degraded.model_copy(update={
        "workflow_id": "healthy-route", "status": "candidate",
        "quality_score": 75, "consecutive_failures": 0,
    })
    llm = _StructuredSelectionLLM(WorkflowSelectionResponse(
        selected_workflow_id=degraded.workflow_id,
        matching_workflow_ids=[degraded.workflow_id, healthy.workflow_id],
        confidence=0.68,
        reason="both routes perform article save draft",
    ))
    service = BrowserWorkflowCacheService(
        repository=_LookupRepository([degraded, healthy]),
        semantic_selector=WorkflowSemanticSelector(llm=llm),
    )
    node = CapabilityTask(
        node_id="save", goal=request, assigned_agent="agent.browser",
        meta={"capability_id": "browser.submit", "browser_site_scope": "mp.weixin.qq.com"},
    )

    matched = asyncio.run(service.lookup(
        user_id="u1", main_id="m", node=node,
        input_context=BrowserInputContext(original_request=request),
    ))

    assert matched is healthy


def test_semantic_selector_keeps_empty_group_as_no_match() -> None:
    request = "删除文章"
    cached = CachedBrowserWorkflow(
        workflow_id="publish-route",
        identity=WorkflowIdentity(
            user_id="u1", site_id="example.test", operation_id="article.publish",
            capability_id="browser.publish", signature_hash="publish-only",
        ),
        steps=[CachedWorkflowStep(
            tool="browser_click", locator={"role": "button", "name": "发布"},
        )],
        request_fingerprint=request_fingerprint(request),
    )
    llm = _StructuredSelectionLLM(WorkflowSelectionResponse(
        selected_workflow_id="",
        matching_workflow_ids=[],
        confidence=0.97,
        reason="delete and publish are different operations",
    ))

    selection = asyncio.run(WorkflowSemanticSelector(llm=llm).select(
        site_id="example.test",
        context=BrowserInputContext(original_request=request),
        current_operation_id="article.delete",
        current_capability_id="browser.delete",
        candidates=[cached],
    ))

    assert selection is None


def test_cache_failure_reporter_persists_feedback() -> None:
    repository = _RecordingRepository()
    service = BrowserWorkflowCacheService(repository=repository)
    workflow = _workflow(type("Compiled", (), {"steps": [], "request_template": None})())

    async def report_failure():
        reporter = service.failure_reporter(workflow)
        assert reporter is not None
        reporter("precondition failed")
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    asyncio.run(report_failure())

    assert repository.failures == [(workflow.workflow_id, "precondition failed")]


class _FailureCollection:
    def __init__(self) -> None:
        self.doc = {
            "_id": "mongo-id",
            "workflow_id": "wf1",
            "status": "active",
            "failure_count": 0,
            "consecutive_failures": 0,
        }

    async def find_one(self, query):
        return dict(self.doc) if query.get("workflow_id") == "wf1" else None

    async def update_one(self, query, update):
        self.doc.update(update["$set"])


def test_repeated_cache_failures_degrade_then_quarantine() -> None:
    collection = _FailureCollection()
    repository = BrowserWorkflowCacheRepository()
    repository._indexes_ready = True
    repository._collection = lambda: collection

    asyncio.run(repository.mark_failure("wf1", "first"))
    assert collection.doc["status"] == "degraded"
    asyncio.run(repository.mark_failure("wf1", "second"))
    assert collection.doc["status"] == "degraded"
    asyncio.run(repository.mark_failure("wf1", "third"))
    assert collection.doc["status"] == "quarantined"
    assert collection.doc["failure_count"] == 3
