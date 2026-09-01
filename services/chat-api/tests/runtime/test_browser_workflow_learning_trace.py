from __future__ import annotations

import asyncio

from app.enterprise_capabilities.browser.engine.checkpoint import BrowserExecutionCheckpoint
from app.enterprise_capabilities.browser.engine.drivers.base import BrowserDriver
from app.enterprise_capabilities.browser.engine.entry_candidates import extract_candidate_entries
from app.enterprise_capabilities.browser.engine.form_input.input_context import BrowserInputContext, InputCandidate
from app.enterprise_capabilities.browser.engine.workflow_cache.admission import terminal_effect_allows_cache
from app.enterprise_capabilities.browser.engine.workflow_cache.compiler import compile_parameterized_workflow
from app.enterprise_capabilities.browser.engine.workflow_cache.contracts import (
    CachedBrowserWorkflow,
    CachedCompletionContract,
    CachedWorkflowStep,
    WorkflowIdentity,
)
from app.enterprise_capabilities.browser.engine.workflow_cache.driver import LearnedWorkflowDriver
from app.enterprise_capabilities.browser.engine.workflow_cache.distiller import distill_field_bindings
from app.enterprise_capabilities.browser.engine.workflow_cache.learning_trace import WorkflowLearningTrace
from app.enterprise_capabilities.browser.engine.workflow_cache.action_policy import (
    REPLAYABLE_ACTION_TOOLS,
    action_disposition,
)
from app.enterprise_capabilities.browser.engine.workflow_cache.matching import (
    request_fingerprint,
    select_matching_workflow,
    workflow_match_score,
)
from app.enterprise_capabilities.browser.engine.workflow_cache.repository import BrowserWorkflowCacheRepository
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation, StepRecord


def _obs(url: str, state: str, elements=None) -> Observation:
    return Observation(
        url=url,
        title="page",
        elements=list(elements or []),
        revision=state,
        state_fingerprint=state,
    )


def _record(before: Observation, after: Observation, tool: str, args: dict) -> StepRecord:
    return StepRecord(
        observation=after,
        decision_observation=before,
        decision=Decision(tool=tool, args=args),
        ok=True,
    )


def _context() -> BrowserInputContext:
    return BrowserInputContext(
        original_request="在公众号把标题和正文都填写测试文字并插入图片后保存草稿",
        candidates=[
            InputCandidate("title", "request", "payload.title", "title", "测试文字"),
            InputCandidate("body", "request", "payload.body", "body", "测试文字"),
            InputCandidate(
                "media", "upstream", "payload.media", "media", ["/tmp/image.png"],
                value_kind="file",
            ),
        ],
    )


def test_learning_trace_survives_auth_pause_and_keeps_complete_form_flow() -> None:
    blank = _obs("about:blank", "s0")
    home = _obs("https://mp.weixin.qq.com/", "s1", [
        {"ref": "draft", "role": "link", "name": "草稿箱", "selector": "#draft"},
    ])
    editor = _obs("https://mp.weixin.qq.com/editor", "s2", [
        {"ref": "title", "role": "textbox", "name": "标题", "selector": "#title"},
        {"ref": "body", "role": "textbox", "name": "正文", "selector": "#body"},
        {"ref": "save", "role": "button", "name": "保存草稿", "selector": "#save"},
    ])
    trace = WorkflowLearningTrace.restore(None, history_size=0)
    before_pause = [
        _record(blank, home, "browser_navigate", {"url": home.url}),
        _record(home, editor, "browser_click", {"ref": "draft"}),
    ]
    trace.capture_new(before_pause)
    checkpoint = BrowserExecutionCheckpoint.capture(
        phase="waiting_auth",
        next_step=3,
        visible_tool_step=2,
        observation=editor,
        history=before_pause,
        authenticated_domains=set(),
        last_safe_url_by_domain={},
        login_recovery_failures={},
        wait_for_text_calls={},
        learning_trace=trace.export(),
    )

    restored_history = checkpoint.restore_history()
    resumed = WorkflowLearningTrace.restore(
        checkpoint.learning_trace,
        history_size=len(restored_history),
    )
    filled_title = _obs(editor.url, "s3", editor.elements)
    filled_body = _obs(editor.url, "s4", editor.elements)
    pasted = _obs(editor.url, "s5", editor.elements)
    saved = _obs("https://mp.weixin.qq.com/drafts/1", "s6")
    restored_history.extend([
        _record(editor, filled_title, "browser_fill", {"ref": "title", "value": "测试文字"}),
        _record(filled_title, filled_body, "browser_fill", {"ref": "body", "value": "测试文字"}),
        _record(filled_body, pasted, "browser_paste_image", {
            "editor_ref": "body", "sources": ["/tmp/image.png"],
        }),
        _record(pasted, saved, "browser_click", {"ref": "save"}),
    ])
    resumed.capture_new(restored_history)
    learned_history = resumed.successful_path(site_id="mp.weixin.qq.com")
    compiled = compile_parameterized_workflow(learned_history, _context())
    bindings = distill_field_bindings(learned_history, _context())

    assert resumed.complete is True
    assert [step.tool for step in compiled.steps] == [
        "browser_navigate", "browser_click", "browser_fill", "browser_fill",
        "browser_paste_image", "browser_click",
    ]
    assert compiled.complete is True
    assert {item.semantic_name for item in bindings} == {"title", "body", "media"}
    serialized = str([step.model_dump() for step in compiled.steps])
    assert "测试文字" not in serialized
    assert "/tmp/image.png" not in serialized


def test_learning_trace_removes_unrelated_prefix_and_navigation_dead_end() -> None:
    trace = WorkflowLearningTrace.restore(None, history_size=0)
    blank = _obs("about:blank", "a")
    image = _obs("https://static.example.net/image.png", "b")
    listing = _obs("https://example.test/list", "c", [
        {"ref": "wrong", "role": "link", "name": "错误项", "selector": "#wrong"},
        {"ref": "right", "role": "link", "name": "正确项", "selector": "#right"},
    ])
    wrong = _obs("https://example.test/wrong", "d", [
        {"ref": "back", "role": "button", "name": "返回", "selector": "#back"},
    ])
    detail = _obs("https://example.test/detail", "e")
    history = [
        _record(blank, image, "browser_navigate", {"url": image.url}),
        _record(image, listing, "browser_navigate", {"url": listing.url}),
        _record(listing, wrong, "browser_click", {"ref": "wrong"}),
        _record(wrong, listing, "browser_click", {"ref": "back"}),
        _record(listing, detail, "browser_click", {"ref": "right"}),
    ]
    trace.capture_new(history)

    path = trace.successful_path(site_id="example.test")

    assert [item.decision.tool for item in path] == ["browser_navigate", "browser_click"]
    assert path[0].decision.args["url"] == listing.url
    assert path[1].decision_observation.elements[0]["name"] == "正确项"


def test_unlocatable_successful_action_blocks_cache_admission() -> None:
    trace = WorkflowLearningTrace.restore(None, history_size=0)
    before = _obs("https://example.test/list", "a", [])
    after = _obs("https://example.test/detail", "b", [])
    trace.capture_new([_record(before, after, "browser_click", {"ref": "missing"})])

    assert trace.complete is False
    assert len(trace.gaps) == 1
    distilled = trace.distill(site_id="example.test")
    assert distilled.complete is False
    assert len(distilled.critical_gaps) == 1


def test_unresolved_human_click_blocks_cache_admission() -> None:
    trace = WorkflowLearningTrace.restore(None, history_size=0)

    trace.capture_recorded([
        {
            "recording_id": "assist-1",
            "sequence": 1,
            "type": "unresolved_click",
            "url": "https://example.test/home",
            "before_url": "https://example.test/home",
            "after_url": "https://example.test/home",
        },
    ], input_context=_context())

    assert trace.complete is False
    assert len(trace.gaps) == 1
    assert trace.gaps[0].tool == "human:unresolved_click"
    assert trace.gaps[0].reason == "unsupported_human_action"


def test_human_recording_preserves_auth_transition_for_compilation() -> None:
    trace = WorkflowLearningTrace.restore(None, history_size=0)
    trace.capture_recorded([
        {
            "recording_id": "assist-auth",
            "sequence": 1,
            "type": "click",
            "before_url": "https://console.example.test/",
            "after_url": "https://console.example.test/home",
            "before_fingerprint": "login",
            "after_fingerprint": "home",
            "before_auth_state": "required",
            "after_auth_state": "authenticated",
            "target": {"selector": "#auth", "role": "button", "name": "Continue"},
        },
    ], input_context=_context())

    path = trace.successful_path(site_id="console.example.test")
    compiled = compile_parameterized_workflow(path, _context())

    assert len(compiled.steps) == 1
    assert compiled.steps[0].execution_kind == "runtime_precondition"
    assert compiled.steps[0].precondition_category == "authentication"


def test_noncritical_locator_gaps_are_removed_with_same_page_exploration_loop() -> None:
    trace = WorkflowLearningTrace.restore(None, history_size=0)
    listing_elements = [
        {"ref": "right", "role": "link", "name": "正确入口", "selector": "#right"},
    ]
    listing = _obs("https://example.test/list", "a", listing_elements)
    wrong_panel = _obs("https://example.test/list", "b", [
        {"ref": "back", "role": "button", "name": "返回", "selector": "#back"},
    ])
    returned = _obs("https://example.test/list", "c", listing_elements)
    detail = _obs("https://example.test/detail", "d")
    trace.capture_new([
        _record(listing, wrong_panel, "browser_click", {"ref": "missing-wrong"}),
        _record(wrong_panel, returned, "browser_click", {"ref": "missing-back"}),
        _record(returned, detail, "browser_click", {"ref": "right"}),
    ])

    distilled = trace.distill(site_id="example.test")
    path = trace.successful_path(site_id="example.test")

    assert len(trace.gaps) == 2
    assert distilled.complete is True
    assert distilled.critical_gaps == []
    assert [record.decision.tool for record in path] == ["browser_click"]
    assert path[0].decision_observation.elements[0]["name"] == "正确入口"


def test_earlier_fill_is_removed_when_same_field_is_overwritten() -> None:
    trace = WorkflowLearningTrace.restore(None, history_size=0)
    form = _obs("https://example.test/form", "a", [
        {"ref": "title", "role": "textbox", "name": "标题", "selector": "#title"},
        {"ref": "save", "role": "button", "name": "保存", "selector": "#save"},
    ])
    wrong = _obs(form.url, "b", form.elements)
    corrected = _obs(form.url, "c", form.elements)
    saved = _obs("https://example.test/saved", "d")
    trace.capture_new([
        _record(form, wrong, "browser_fill", {"ref": "title", "value": "错误标题"}),
        _record(wrong, corrected, "browser_fill", {"ref": "title", "value": "正确标题"}),
        _record(corrected, saved, "browser_click", {"ref": "save"}),
    ])

    path = trace.successful_path(site_id="example.test")

    assert [record.decision.tool for record in path] == ["browser_fill", "browser_click"]
    assert path[0].decision.args["value"] == "正确标题"


def test_terminal_commit_is_kept_even_when_page_returns_to_prior_visual_state() -> None:
    trace = WorkflowLearningTrace.restore(None, history_size=0)
    form = _obs("https://example.test/form", "a", [
        {"ref": "save", "role": "button", "name": "保存", "selector": "#save"},
    ])
    transient = _obs(form.url, "b", [
        {"ref": "save", "role": "button", "name": "保存", "selector": "#save"},
        {"ref": "spinner", "role": "status", "name": "保存中"},
    ])
    returned = _obs(form.url, "c", form.elements)
    trace.capture_new([
        _record(form, transient, "browser_wait_for", {"timeout": 500}),
        _record(transient, returned, "browser_click", {"ref": "save"}),
        _record(returned, returned, "browser_wait_for", {"timeout": 500}),
    ])

    path = trace.successful_path(site_id="example.test")

    commit = next(record for record in path if record.decision.tool == "browser_click")
    assert commit.decision_observation.elements[0]["name"] == "保存"


def test_wait_for_is_a_shared_replayable_action_not_a_trace_gap() -> None:
    trace = WorkflowLearningTrace()
    before = _obs("https://example.test/form", "a")
    ready = _obs("https://example.test/form", "b", [
        {"ref": "save", "role": "button", "name": "保存", "selector": "#save"},
    ])
    trace.capture_new([
        _record(before, ready, "browser_wait_for", {
            "text": "编辑器已就绪", "timeout": 3000,
        }),
    ])

    compiled = compile_parameterized_workflow(
        trace.successful_path(site_id="example.test"),
        BrowserInputContext(original_request="等待编辑器并继续"),
    )

    assert action_disposition("browser_wait_for") == "replay"
    assert "browser_wait_for" in REPLAYABLE_ACTION_TOOLS
    assert trace.complete is True
    assert trace.gaps == []
    assert len(compiled.steps) == 1
    assert compiled.steps[0].tool == "browser_wait_for"
    assert compiled.steps[0].args == {"text": "编辑器已就绪", "timeout": 3000}


def test_compiler_inserts_readiness_barrier_after_scroll_before_interaction() -> None:
    context = BrowserInputContext(original_request="打开内容管理")
    before = _obs("https://example.test/home", "a", [
        {"ref": "content", "role": "menuitem", "name": "内容管理", "selector": "li:nth-of-type(3)"},
    ])
    scrolled = _obs(before.url, "b", before.elements)
    opened = _obs(before.url, "c", before.elements)

    compiled = compile_parameterized_workflow([
        _record(before, scrolled, "browser_scroll", {"direction": "down"}),
        _record(scrolled, opened, "browser_click", {"ref": "content"}),
    ], context)

    assert [step.tool for step in compiled.steps] == [
        "browser_scroll", "browser_wait_for", "browser_click",
    ]
    assert compiled.steps[1].args == {"text": "内容管理", "timeout": 5000}


def test_ref_only_wait_is_converted_to_a_stable_semantic_locator() -> None:
    trace = WorkflowLearningTrace()
    before = _obs("https://example.test/form", "a", [
        {"ref": "live-17", "role": "button", "name": "提交", "selector": "#submit"},
    ])
    after = _obs(before.url, "b", before.elements)
    trace.capture_new([
        _record(before, after, "browser_wait_for", {"ref": "live-17", "timeout": 2000}),
    ])

    compiled = compile_parameterized_workflow(
        trace.successful_path(site_id="example.test"),
        BrowserInputContext(original_request="等待提交按钮"),
    )

    assert trace.complete is True
    assert compiled.complete is True
    assert compiled.steps[0].locator["selector"] == "#submit"
    assert "ref" not in compiled.steps[0].args


def test_unlocatable_ref_only_wait_blocks_cache_as_nonportable() -> None:
    trace = WorkflowLearningTrace()
    before = _obs("https://example.test/form", "a")
    trace.capture_new([
        _record(before, before, "browser_wait_for", {"ref": "stale-ref", "timeout": 1000}),
    ])

    assert trace.complete is False
    assert [gap.reason for gap in trace.gaps] == ["stable_locator_missing"]


def test_delay_waits_do_not_make_an_otherwise_complete_success_route_incomplete() -> None:
    trace = WorkflowLearningTrace()
    form = _obs("https://example.test/form", "a", [
        {"ref": "save", "role": "button", "name": "保存", "selector": "#save"},
    ])
    ready = _obs(form.url, "b", form.elements)
    saved = _obs("https://example.test/saved", "c")
    trace.capture_new([
        _record(form, form, "browser_wait_for", {"timeout": 300}),
        _record(form, ready, "browser_wait_for", {"timeout": 500}),
        _record(ready, saved, "browser_click", {"ref": "save"}),
    ])

    distilled = trace.distill(site_id="example.test")

    assert trace.gaps == []
    assert distilled.complete is True
    assert distilled.critical_gaps == []
    assert [entry.tool for entry in distilled.entries][-1] == "browser_click"


def test_human_assistance_control_marker_does_not_poison_merged_success_route() -> None:
    trace = WorkflowLearningTrace()
    form = _obs("https://example.test/form", "a", [
        {"ref": "save", "role": "button", "name": "保存", "selector": "#save"},
    ])
    saved = _obs("https://example.test/saved", "b")
    trace.capture_new([
        _record(form, form, "browser_ask_user", {"question": "请完成验证码"}),
        _record(form, saved, "browser_click", {"ref": "save"}),
    ])

    assert action_disposition("browser_ask_user") == "ignore"
    assert trace.gaps == []
    assert [item.decision.tool for item in trace.successful_path(site_id="example.test")] == [
        "browser_click",
    ]


def test_resource_url_is_not_used_as_browser_entry_for_another_target_site() -> None:
    entries = extract_candidate_entries(
        "请下载 https://static.example.com/a.png然后到微信公众号保存草稿",
        [],
        expected_site="mp.weixin.qq.com",
    )

    assert entries == [{
        "url": "https://mp.weixin.qq.com/",
        "source": "site_scope",
        "name": "mp.weixin.qq.com",
    }]


def test_bare_target_domain_is_not_swallowed_by_preceding_resource_url_text() -> None:
    entries = extract_candidate_entries(
        "https://static.example.com/a.png请下载，然后浏览器打开publisher.example.com，保存草稿",
        [],
        expected_site="publisher.example.com",
    )

    assert entries == [{
        "url": "https://publisher.example.com",
        "source": "user_request",
        "name": "",
    }]


def test_write_cache_admission_requires_last_effect_to_be_confirmed() -> None:
    assert terminal_effect_allows_cache("browser.read", []) is True
    assert terminal_effect_allows_cache(
        "browser.submit", [{"status": "confirmed_success"}, {"status": "unknown"}],
    ) is False
    assert terminal_effect_allows_cache(
        "browser.submit", [{"status": "unknown"}, {"status": "confirmed_success"}],
    ) is True


class _FallbackDriver(BrowserDriver):
    kind = "fallback"

    async def next_step(self, goal, history, observation, state_ledger=None):
        return Decision(tool="browser_done", args={})


def test_learned_driver_cursor_continues_after_auth_checkpoint() -> None:
    identity = WorkflowIdentity(
        user_id="u1", site_id="example.test", operation_id="resource.navigate",
        capability_id="browser.navigate", signature_hash="sig",
    )
    workflow = CachedBrowserWorkflow(
        workflow_id="wf-auth",
        identity=identity,
        steps=[
            CachedWorkflowStep(
                tool="browser_navigate",
                args={"url": "https://example.test/"},
                target_url_shape="example.test/",
            ),
            CachedWorkflowStep(
                tool="browser_click",
                locator={"role": "link", "name": "控制台"},
                source_url_shape="example.test/",
                target_url_shape="example.test/console",
                expect_state_change=True,
            ),
        ],
    )
    context = BrowserInputContext(original_request="打开示例站控制台")
    first_driver = LearnedWorkflowDriver(
        workflow=workflow, fallback=_FallbackDriver(), input_context=context,
    )
    blank = _obs("about:blank", "a")
    navigate = asyncio.run(first_driver.next_step("打开控制台", [], blank))
    logged_in = _obs("https://example.test/", "b", [
        {"ref": "console-new", "role": "link", "name": "控制台"},
    ])
    first_driver.on_step_completed(navigate, True, logged_in)
    state = first_driver.export_checkpoint_state()

    resumed_driver = LearnedWorkflowDriver(
        workflow=workflow, fallback=_FallbackDriver(), input_context=context,
    )
    resumed_driver.restore_checkpoint_state(state)
    decision = asyncio.run(resumed_driver.next_step("打开控制台", [], logged_in))

    assert decision.tool == "browser_click"
    assert decision.args["ref"] == "console-new"


class _VersionCollection:
    def __init__(self) -> None:
        self.docs = []

    async def find_one(self, query):
        for doc in self.docs:
            if all(_matches(doc, key, value) for key, value in query.items()):
                return dict(doc)
        return None

    async def insert_one(self, doc):
        row = dict(doc)
        row.setdefault("_id", len(self.docs) + 1)
        self.docs.append(row)

    async def update_one(self, query, update):
        for doc in self.docs:
            if all(_matches(doc, key, value) for key, value in query.items()):
                doc.update(update["$set"])
                return

    async def update_many(self, query, update):
        for doc in self.docs:
            if all(_matches(doc, key, value) for key, value in query.items()):
                doc.update(update["$set"])


def _matches(doc, key, wanted):
    actual = doc
    for part in key.split("."):
        actual = actual.get(part) if isinstance(actual, dict) else None
    if isinstance(wanted, dict) and "$ne" in wanted:
        return actual != wanted["$ne"]
    return actual == wanted


def test_repaired_plan_becomes_champion_without_overwriting_old_plan() -> None:
    repository = BrowserWorkflowCacheRepository()
    repository._indexes_ready = True
    collection = _VersionCollection()
    repository._collection = lambda: collection
    identity = WorkflowIdentity(
        user_id="u1", site_id="example.test", operation_id="article.save_draft",
        capability_id="browser.submit", signature_hash="signature",
    )
    completion = CachedCompletionContract(capability_id="browser.submit")

    async def save(plan_hash: str, *, replayed=False, matched="", failed=False):
        return await repository.upsert_success(
            identity=identity,
            steps=[],
            field_bindings=[],
            request_template=None,
            request_fingerprint="request",
            completion=completion,
            dynamic_input_roles=[],
            run_id="run",
            replayed=replayed,
            plan_hash=plan_hash,
            quality_score=90,
            matched_workflow_id=matched,
            replay_failed=failed,
        )

    first = asyncio.run(save("old"))
    champion = asyncio.run(save("old", replayed=True, matched=first.workflow_id))
    repaired = asyncio.run(save(
        "new", replayed=True, matched=champion.workflow_id, failed=True,
    ))
    promoted = asyncio.run(save(
        "new", replayed=True, matched=repaired.workflow_id, failed=False,
    ))

    assert len(collection.docs) == 2
    assert repaired.status == "candidate"
    assert repaired.supersedes_workflow_id == champion.workflow_id
    assert promoted.status == "active"
    old = next(item for item in collection.docs if item["workflow_id"] == champion.workflow_id)
    assert old["status"] == "degraded"


def test_materially_better_challenger_gets_guarded_replay_trial() -> None:
    context = BrowserInputContext(original_request="处理本次订单")
    identity = WorkflowIdentity(
        user_id="u1", site_id="example.test", operation_id="order.update",
        capability_id="browser.modify", signature_hash="sig",
    )
    fingerprint = request_fingerprint(context.original_request)
    active = CachedBrowserWorkflow(
        workflow_id="active",
        identity=identity,
        status="active",
        quality_score=88,
        replay_success_count=1,
        request_fingerprint=fingerprint,
    )
    challenger = CachedBrowserWorkflow(
        workflow_id="challenger",
        identity=identity,
        status="candidate",
        quality_score=100,
        request_fingerprint=fingerprint,
    )

    selected = select_matching_workflow(
        [active, challenger], context=context, capability_id="browser.modify",
    )

    assert selected is not None
    assert selected.workflow_id == "challenger"


def test_structured_form_cache_matches_changed_wording_and_business_values() -> None:
    old_context = _context()
    editor = _obs("https://mp.weixin.qq.com/editor", "a", [
        {"ref": "title", "role": "textbox", "name": "标题", "selector": "#title"},
        {"ref": "body", "role": "textbox", "name": "正文", "selector": "#body"},
    ])
    compiled = compile_parameterized_workflow([
        _record(editor, _obs(editor.url, "b"), "browser_fill", {
            "ref": "title", "value": "测试文字",
        }),
        _record(editor, _obs(editor.url, "c"), "browser_fill", {
            "ref": "body", "value": "测试文字",
        }),
    ], old_context)
    identity = WorkflowIdentity(
        user_id="u1", site_id="mp.weixin.qq.com", operation_id="article.save_draft",
        capability_id="browser.submit", signature_hash="sig",
    )
    workflow = CachedBrowserWorkflow(
        workflow_id="form",
        identity=identity,
        version=3,
        status="candidate",
        steps=compiled.steps,
        request_template=compiled.request_template,
        request_fingerprint=request_fingerprint(old_context.original_request),
        dynamic_input_roles=["title", "body", "media"],
    )
    new_context = BrowserInputContext(
        original_request="请另存一篇完全不同内容的公众号草稿",
        candidates=[
            InputCandidate("title2", "request", "payload.title", "title", "新标题"),
            InputCandidate("body2", "request", "payload.body", "body", "新的长正文"),
            InputCandidate("media2", "upstream", "payload.media", "media", ["/tmp/new.png"], value_kind="file"),
        ],
    )

    assert compiled.request_template is None
    assert workflow_match_score(
        workflow, context=new_context, capability_id="browser.submit",
    ) >= 0
