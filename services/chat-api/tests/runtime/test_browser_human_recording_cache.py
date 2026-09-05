from __future__ import annotations

import asyncio

from app.enterprise_capabilities.browser.engine.form_input.input_context import BrowserInputContext, InputCandidate
from app.enterprise_capabilities.browser.engine.workflow_cache.contracts import (
    CachedBrowserWorkflow,
    CachedCompletionContract,
    CachedWorkflowStep,
    WorkflowIdentity,
)
from app.enterprise_capabilities.browser.engine.workflow_cache.coverage import (
    assess_cached_workflow,
    assess_compiled_workflow,
)
from app.enterprise_capabilities.browser.engine.workflow_cache.learning_trace import WorkflowLearningTrace
from app.enterprise_capabilities.browser.engine.workflow_cache.compiler import compile_parameterized_workflow
from app.enterprise_capabilities.browser.engine.workflow_cache.manual_capture import capture_manual_recording
from app.enterprise_capabilities.browser.engine.workflow_cache.manual_analysis import (
    ManualRecordingAnalyzer,
    ManualWorkflowClassification,
)
from app.enterprise_capabilities.browser.engine.workflow_cache.manual_events import normalize_manual_events
from app.enterprise_capabilities.browser.engine.workflow_cache.manual_plan import build_manual_recording_plan
from app.enterprise_capabilities.browser.engine.workflow_cache.recorded_target_identity import (
    stabilize_recorded_target_identities,
)
from app.enterprise_capabilities.browser.engine.workflow_cache.service import BrowserWorkflowCacheService
from app.enterprise_capabilities.browser.engine.recording.store import HumanRecordingStore
from app.browser.registry import AgentRegistry


def _events(*, terminal: bool = True) -> list[dict]:
    events = [
        {"recording_id": "r1", "sequence": 0, "type": "recording_started", "url": "https://cms.example.test/editor"},
        {"recording_id": "r1", "sequence": 1, "type": "fill", "value": "本次标题", "target": {"role": "textbox", "name": "标题", "selector": "#title"}, "before_url": "https://cms.example.test/editor", "after_url": "https://cms.example.test/editor", "before_fingerprint": "s1", "after_fingerprint": "s2"},
        {"recording_id": "r1", "sequence": 2, "type": "fill", "value": "<p>本次正文</p>", "target": {"role": "textbox", "name": "正文", "selector": "#body"}, "before_url": "https://cms.example.test/editor", "after_url": "https://cms.example.test/editor", "before_fingerprint": "s2", "after_fingerprint": "s3"},
        {"recording_id": "r1", "sequence": 3, "type": "paste_image", "target": {"role": "textbox", "name": "正文", "selector": "#body", "semanticPurpose": "upload"}, "before_url": "https://cms.example.test/editor", "after_url": "https://cms.example.test/editor", "before_fingerprint": "s3", "after_fingerprint": "s4"},
    ]
    if terminal:
        events.append({"recording_id": "r1", "sequence": 4, "type": "click", "target": {"role": "button", "name": "保存草稿", "selector": "#save", "semanticPurpose": "save"}, "before_url": "https://cms.example.test/editor", "after_url": "https://cms.example.test/drafts/1", "before_fingerprint": "s4", "after_fingerprint": "s5"})
    events.append({"recording_id": "r1", "sequence": 5, "type": "recording_stopped", "url": "https://cms.example.test/drafts/1"})
    return events


def _context() -> BrowserInputContext:
    return BrowserInputContext(
        original_request="发布带图文章",
        candidates=[
            InputCandidate("title", "upstream", "payload.title", "title", "本次标题"),
            InputCandidate("body", "upstream", "payload.body", "body", "<p>本次正文</p>"),
            InputCandidate("media", "upstream", "payload.media", "visual_assets", ["/tmp/current.png"], value_kind="file"),
        ],
    )


def test_human_actions_merge_into_parameterized_complete_route() -> None:
    trace = WorkflowLearningTrace()
    trace.capture_recorded(_events(), input_context=_context())

    path = trace.successful_path(site_id="cms.example.test")

    assert trace.complete is True
    assert [record.decision.tool for record in path] == [
        "browser_fill", "browser_fill", "browser_paste_image", "browser_click",
    ]
    assert all(entry.provenance == "human" for entry in trace.entries)


def test_human_recording_drops_no_effect_noise_but_keeps_async_terminal_click() -> None:
    events = _events()
    events.insert(1, {
        "recording_id": "r1", "sequence": 0, "type": "click",
        "target": {"selector": "#page", "name": "页面空白处"},
        "before_url": "https://cms.example.test/editor",
        "after_url": "https://cms.example.test/editor",
        "before_fingerprint": "s1", "after_fingerprint": "s1",
    })
    terminal = next(item for item in events if item.get("sequence") == 4)
    terminal["after_url"] = terminal["before_url"]
    terminal["after_fingerprint"] = terminal["before_fingerprint"]
    trace = WorkflowLearningTrace()
    trace.capture_recorded(events, input_context=_context())

    path = trace.successful_path(site_id="cms.example.test")
    compiled = compile_parameterized_workflow(path, _context())

    assert "页面空白处" not in str(trace.export())
    assert any(entry.locator.get("semanticPurpose") == "save" for entry in trace.entries)
    assert compiled.complete is True
    assert compiled.skipped_actions == 0
    assert compiled.steps[-1].tool == "browser_click"


def test_manual_event_normalization_collapses_reactive_field_mirrors_generically() -> None:
    url = "https://cms.example.test/editor"
    events = [
        {"sequence": 1, "type": "fill", "value": "旧标题", "target": {"selector": "#title", "role": "textbox", "placeholder": "标题"}, "url": url},
        {"sequence": 2, "type": "fill", "value": "旧标题", "target": {"selector": "body > main > div:nth-of-type(8)", "role": "textbox", "name": "旧标题"}, "url": url},
        {"sequence": 3, "type": "press", "key": "Tab", "target": {"selector": "body > main > div:nth-of-type(8)", "role": "textbox", "name": "最终标题"}, "url": url},
        # Debounced mirror events arrive after keydown but describe the value
        # that was entered before Tab.
        {"sequence": 4, "type": "fill", "value": "最终标题", "target": {"selector": "body > main > div:nth-of-type(8)", "role": "textbox", "name": "最终标题"}, "url": url},
        {"sequence": 5, "type": "fill", "value": "最终标题", "target": {"selector": "#title", "role": "textbox", "placeholder": "标题"}, "url": url},
        {"sequence": 6, "type": "click", "target": {"selector": "#body", "role": "textbox", "name": "正文"}, "url": url},
    ]

    normalized = normalize_manual_events(events)

    fills = [item for item in normalized.events if item["type"] == "fill"]
    assert len(fills) == 1
    assert fills[0]["value"] == "最终标题"
    assert fills[0]["target"]["selector"] == "#title"
    assert [item["type"] for item in normalized.events[:2]] == ["fill", "press"]
    assert normalized.discarded_mutations == 3


def test_manual_event_normalization_keeps_distinct_business_fields() -> None:
    events = [
        {"sequence": 1, "type": "fill", "value": "相同内容", "target": {"selector": "#title", "name": "标题"}, "url": "https://cms.example.test/editor"},
        {"sequence": 2, "type": "fill", "value": "相同内容", "target": {"selector": "#body", "name": "正文"}, "url": "https://cms.example.test/editor"},
    ]

    normalized = normalize_manual_events(events)

    assert [item["target"]["selector"] for item in normalized.events] == ["#title", "#body"]


def test_manual_event_normalization_discards_only_noncausal_unresolved_clicks() -> None:
    url = "https://cms.example.test/editor"
    events = [
        {
            "sequence": 1, "type": "unresolved_click",
            "before_url": url, "after_url": url,
            "before_fingerprint": "same", "after_fingerprint": "same",
        },
        {
            "sequence": 2, "type": "unresolved_click",
            "before_url": url, "after_url": f"{url}/next",
            "before_fingerprint": "same", "after_fingerprint": "changed",
        },
    ]

    normalized = normalize_manual_events(events)

    assert [item["sequence"] for item in normalized.events] == [2]
    assert normalized.discarded_diagnostics == 1


def test_manual_recording_admits_route_with_incidental_unresolved_click() -> None:
    events = _events()
    events.insert(1, {
        "recording_id": "r1", "sequence": 0, "type": "unresolved_click",
        "before_url": "https://cms.example.test/editor",
        "after_url": "https://cms.example.test/editor",
        "before_fingerprint": "s1", "after_fingerprint": "s1",
    })

    plan = build_manual_recording_plan(
        events=events,
        operation="保存带图文章草稿",
        capability_id="browser.submit",
    )

    assert plan.complete is True
    assert "unsupported_human_action" not in plan.reasons


def test_recorded_target_identity_survives_value_driven_accessible_name_changes() -> None:
    selector = "body > main:nth-of-type(2) > div:nth-child(7)"
    url = "https://cms.example.test/editor"
    events = [
        {"sequence": 1, "type": "click", "target": {
            "selector": selector, "role": "textbox", "name": "从这里开始写正文",
        }, "before_url": url},
        {"sequence": 2, "type": "fill", "value": "<p>本次正文</p>", "target": {
            "selector": selector, "role": "textbox", "name": "本次正文",
        }, "before_url": url},
        {"sequence": 3, "type": "click", "target": {
            "selector": selector, "role": "textbox", "name": "本次正文",
        }, "before_url": url},
    ]

    stabilized = stabilize_recorded_target_identities(events)

    assert [item["target"]["name"] for item in stabilized] == [
        "从这里开始写正文", "从这里开始写正文", "从这里开始写正文",
    ]


def test_recorded_target_identity_does_not_cross_frame_or_control_boundaries() -> None:
    url = "https://cms.example.test/editor"
    selector = "body > div:nth-child(2)"
    events = [
        {"sequence": 1, "type": "click", "target": {
            "selector": selector, "frameDepth": 1, "role": "textbox", "name": "正文",
        }, "before_url": url},
        {"sequence": 2, "type": "fill", "value": "动态值", "target": {
            "selector": selector, "frameDepth": 2, "role": "textbox", "name": "动态值",
        }, "before_url": url},
        {"sequence": 3, "type": "fill", "value": "另一个值", "target": {
            "selector": "body > div:nth-child(3)", "frameDepth": 1,
            "role": "textbox", "name": "另一个值",
        }, "before_url": url},
        {"sequence": 4, "type": "fill", "value": "新标签值", "target": {
            "selector": selector, "frameDepth": 1, "role": "textbox", "name": "新标签值",
        }, "before_url": url, "before_tab_id": "tab-b"},
    ]

    stabilized = stabilize_recorded_target_identities(events)

    assert "name" not in stabilized[1]["target"]
    assert "name" not in stabilized[2]["target"]
    assert "name" not in stabilized[3]["target"]


def test_recorded_target_identity_canonicalizes_recorder_locator_aliases() -> None:
    selector = "main > div:nth-child(2)"
    url = "https://cms.example.test/editor"

    stabilized = stabilize_recorded_target_identities([
        {"sequence": 1, "type": "click", "target": {
            "selector": selector, "role": "textbox", "aria_label": "正文",
        }, "before_url": url},
        {"sequence": 2, "type": "fill", "value": "动态正文", "target": {
            "selector": selector, "role": "textbox", "name": "动态正文",
        }, "before_url": url},
    ])

    assert stabilized[1]["target"]["name"] == "正文"
    assert "aria_label" not in stabilized[1]["target"]


def test_manual_plan_recovers_stable_rich_editor_identity_before_click_filtering() -> None:
    url = "https://cms.example.test/editor"
    selector = "body > main:nth-of-type(2) > div:nth-child(7)"
    events = [
        {"sequence": 0, "type": "recording_started", "url": url},
        {"sequence": 1, "type": "click", "target": {
            "selector": selector, "role": "textbox", "name": "从这里开始写正文",
        }, "before_url": url, "after_url": url,
         "before_fingerprint": "same", "after_fingerprint": "same"},
        {"sequence": 2, "type": "fill", "value": "<p>本次正文</p>", "target": {
            "selector": selector, "role": "textbox", "name": "本次正文",
        }, "before_url": url, "after_url": url,
         "before_fingerprint": "same", "after_fingerprint": "filled"},
        {"sequence": 3, "type": "click", "target": {
            "selector": "#save", "role": "button", "name": "保存",
            "semanticPurpose": "save",
        }, "before_url": url, "after_url": url,
         "before_fingerprint": "filled", "after_fingerprint": "saved"},
        {"sequence": 4, "type": "recording_stopped", "url": url},
    ]

    plan = build_manual_recording_plan(
        events=events,
        operation="填写正文并保存",
        capability_id="browser.submit",
    )

    assert plan.complete is True
    assert plan.compiled.steps[0].tool == "browser_fill"
    assert plan.compiled.steps[0].locator == {
        "role": "textbox", "name": "从这里开始写正文",
    }


def test_manual_plan_recovers_identity_before_reactive_fill_compaction() -> None:
    url = "https://cms.example.test/editor?session=current"
    selector = "body > main:nth-of-type(2) > div:nth-child(7)"
    events = [
        {"sequence": 0, "type": "recording_started", "url": url},
        {"sequence": 1, "type": "fill", "value": "<p>temporary</p>", "target": {
            "selector": selector, "role": "textbox", "name": "temporary",
        }, "before_url": url, "after_url": url,
         "before_fingerprint": "empty", "after_fingerprint": "temporary"},
        {"sequence": 2, "type": "fill", "value": (
            '<div contenteditable="false">从这里开始写正文</div><p><br></p>'
        ), "target": {
            "selector": selector, "role": "textbox", "name": "从这里开始写正文",
        }, "before_url": url, "after_url": url,
         "before_fingerprint": "temporary", "after_fingerprint": "empty-again"},
        {"sequence": 3, "type": "fill", "value": "<p>最终正文</p>", "target": {
            "selector": selector, "role": "textbox", "name": "最终正文",
        }, "before_url": url, "after_url": url,
         "before_fingerprint": "empty-again", "after_fingerprint": "filled"},
        {"sequence": 4, "type": "click", "target": {
            "selector": "#save", "role": "button", "name": "保存",
            "semanticPurpose": "save",
        }, "before_url": url, "after_url": url,
         "before_fingerprint": "filled", "after_fingerprint": "saved"},
        {"sequence": 5, "type": "recording_stopped", "url": url},
    ]

    plan = build_manual_recording_plan(
        events=events,
        operation="填写正文并保存",
        capability_id="browser.submit",
    )

    assert plan.complete is True
    assert [step.tool for step in plan.compiled.steps] == ["browser_fill", "browser_click"]
    assert plan.compiled.steps[0].locator == {
        "role": "textbox", "name": "从这里开始写正文",
    }


def test_file_input_change_is_upload_only_not_an_empty_fill() -> None:
    events = _events()
    events.insert(-1, {
        "recording_id": "r1", "sequence": 4, "type": "fill", "value": "",
        "target": {"selector": "#file", "type": "file", "accept": "image/*"},
        "url": "https://cms.example.test/editor",
    })

    plan = build_manual_recording_plan(
        events=events,
        operation="保存带图片的文章草稿",
        capability_id="browser.submit",
    )

    assert plan.complete is True
    assert plan.compiled.skipped_actions == 0
    assert not any(
        item.get("type") == "fill" and (item.get("target") or {}).get("type") == "file"
        for item in plan.action_events
    )


def test_manual_popup_blank_does_not_erase_the_route_that_opened_it() -> None:
    events = [
        {"recording_id": "r-popup", "sequence": 0, "type": "recording_started", "url": "about:blank"},
        {"recording_id": "r-popup", "sequence": 1, "type": "navigate", "before_url": "about:blank", "after_url": "https://cms.example.test/home", "before_fingerprint": "blank", "after_fingerprint": "home"},
        {"recording_id": "r-popup", "sequence": 2, "type": "click", "target": {"selector": "#drafts", "role": "link", "name": "草稿箱"}, "before_url": "https://cms.example.test/home", "after_url": "https://cms.example.test/drafts", "before_fingerprint": "home", "after_fingerprint": "drafts"},
        # The click opens a fresh tab whose first observable document is blank.
        {"recording_id": "r-popup", "sequence": 3, "type": "click", "target": {"selector": "#create", "role": "button", "name": "新的创作"}, "before_url": "https://cms.example.test/drafts", "after_url": "about:blank", "before_fingerprint": "drafts", "after_fingerprint": "blank"},
        {"recording_id": "r-popup", "sequence": 4, "type": "navigate", "before_url": "about:blank", "after_url": "https://cms.example.test/editor", "before_fingerprint": "blank", "after_fingerprint": "editor"},
        {"recording_id": "r-popup", "sequence": 5, "type": "fill", "value": "标题", "target": {"selector": "#title", "role": "textbox", "name": "标题"}, "before_url": "https://cms.example.test/editor", "after_url": "https://cms.example.test/editor", "before_fingerprint": "editor", "after_fingerprint": "filled"},
        {"recording_id": "r-popup", "sequence": 6, "type": "click", "target": {"selector": "#save", "role": "button", "name": "保存", "semanticPurpose": "save"}, "before_url": "https://cms.example.test/editor", "after_url": "https://cms.example.test/editor", "before_fingerprint": "filled", "after_fingerprint": "saved"},
        {"recording_id": "r-popup", "sequence": 7, "type": "recording_stopped", "url": "https://cms.example.test/editor"},
    ]

    plan = build_manual_recording_plan(
        events=events,
        operation="新建文章并保存",
        capability_id="browser.submit",
    )

    assert plan.complete is True
    assert [record.decision.tool for record in plan.history] == [
        "browser_navigate", "browser_click", "browser_click",
        "browser_fill", "browser_click",
    ]
    popup_click = plan.compiled.steps[2]
    assert popup_click.tool == "browser_click"
    assert popup_click.target_url_shape == "cms.example.test/editor"


def test_loop_erasure_does_not_cross_tab_identity() -> None:
    events = [
        {"recording_id": "r-tabs", "sequence": 0, "type": "recording_started", "url": "https://app.example.test/list"},
        {"recording_id": "r-tabs", "sequence": 1, "type": "click", "target": {"selector": "#open", "role": "link", "name": "打开"}, "before_url": "https://app.example.test/list", "after_url": "https://app.example.test/list", "before_fingerprint": "same", "after_fingerprint": "same", "before_tab_id": "tab-a", "after_tab_id": "tab-b"},
        {"recording_id": "r-tabs", "sequence": 2, "type": "navigate", "before_url": "https://app.example.test/list", "after_url": "https://app.example.test/editor", "before_fingerprint": "same", "after_fingerprint": "editor", "before_tab_id": "tab-b", "after_tab_id": "tab-b"},
        {"recording_id": "r-tabs", "sequence": 3, "type": "click", "target": {"selector": "#save", "role": "button", "name": "保存", "semanticPurpose": "save"}, "before_url": "https://app.example.test/editor", "after_url": "https://app.example.test/editor", "before_fingerprint": "editor", "after_fingerprint": "saved", "before_tab_id": "tab-b", "after_tab_id": "tab-b"},
        {"recording_id": "r-tabs", "sequence": 4, "type": "recording_stopped", "url": "https://app.example.test/editor"},
    ]

    plan = build_manual_recording_plan(
        events=events,
        operation="打开编辑器并保存",
        capability_id="browser.submit",
    )

    assert [record.decision.tool for record in plan.history] == [
        "browser_click", "browser_click",
    ]


def test_redacted_login_value_is_never_added_to_learning_trace() -> None:
    trace = WorkflowLearningTrace()
    trace.capture_recorded([
        {"recording_id": "r", "sequence": 1, "type": "fill", "value_redacted": True, "value": "secret", "target": {"role": "textbox", "name": "密码", "selector": "#password"}, "url": "https://example.test/login"},
        {"recording_id": "r", "sequence": 2, "type": "press", "key": "Enter", "target": {"role": "textbox", "name": "搜索", "selector": "#query"}, "before_url": "https://example.test", "after_url": "https://example.test/results"},
    ], input_context=BrowserInputContext(original_request="搜索", candidates=[]))

    assert len(trace.entries) == 1
    assert trace.entries[0].tool == "browser_press"
    assert "secret" not in str(trace.export())


def test_coverage_rejects_missing_media_and_missing_terminal_action() -> None:
    result = assess_compiled_workflow(
        steps=[CachedWorkflowStep(tool="browser_fill", locator={"name": "标题"})],
        context=_context(),
        capability_id="browser.publish",
        dynamic_roles=["title", "body", "visual_assets"],
    )

    assert result.allowed is False
    assert set(result.reasons) == {
        "required_media_action_missing", "terminal_business_action_missing",
    }


def test_legacy_incomplete_workflow_is_not_replayable() -> None:
    workflow = CachedBrowserWorkflow(
        workflow_id="legacy",
        identity=WorkflowIdentity(
            user_id="u", site_id="cms.example.test", operation_id="article.save_draft",
            capability_id="browser.submit", signature_hash="sig",
        ),
        completion=CachedCompletionContract(capability_id="browser.submit"),
        dynamic_input_roles=["title", "body", "images"],
        steps=[CachedWorkflowStep(tool="browser_fill", locator={"name": "标题"})],
    )

    result = assess_cached_workflow(workflow)

    assert result.allowed is False
    assert "required_media_action_missing" in result.reasons


class _Repo:
    def __init__(self) -> None:
        self.saved = []

    async def upsert_success(self, **kwargs):
        self.saved.append(kwargs)
        return CachedBrowserWorkflow(
            workflow_id="saved",
            identity=kwargs["identity"],
            steps=kwargs["steps"],
            completion=kwargs["completion"],
            dynamic_input_roles=kwargs["dynamic_input_roles"],
        )


class _FailingRepo:
    async def upsert_success(self, **_kwargs):
        raise RuntimeError("write failed")


def test_explicit_manual_recording_uses_same_cache_pipeline() -> None:
    async def run() -> None:
        repo = _Repo()
        cache = BrowserWorkflowCacheService(repository=repo)  # type: ignore[arg-type]
        accepted, reason = await capture_manual_recording(
            cache=cache,
            user_id="u1",
            main_id="m1",
            recording_id="r1",
            operation="保存带图片的文章草稿",
            events=_events(),
        )
        assert accepted is True
        assert reason == "accepted"
        assert len(repo.saved) == 1
        assert repo.saved[0]["display_name"] == "保存带图片的文章草稿"
        tools = [step.tool for step in repo.saved[0]["steps"]]
        assert "browser_paste_image" in tools
        assert tools[-1] == "browser_click"
        serialized = str([step.model_dump() for step in repo.saved[0]["steps"]])
        assert "本次标题" not in serialized
        assert "本次正文" not in serialized

    asyncio.run(run())


def test_manual_recording_without_terminal_action_is_rejected() -> None:
    async def run() -> None:
        cache = BrowserWorkflowCacheService(repository=_Repo())  # type: ignore[arg-type]
        accepted, reason = await capture_manual_recording(
            cache=cache,
            user_id="u1",
            main_id="m1",
            recording_id="r1",
            operation="保存带图片的文章草稿",
            events=_events(terminal=False),
        )

        assert accepted is False
        assert reason == "terminal_business_action_missing"

    asyncio.run(run())


def test_recording_analysis_generates_name_and_reconciles_terminal_capability() -> None:
    class _NamingLLM:
        async def ainvoke_structured(self, _messages, schema, **_kwargs):
            assert schema is ManualWorkflowClassification
            return schema(
                display_name="微信公众号带图文章草稿",
                operation="在微信公众号新建带图文章并保存草稿",
                capability_id="browser.navigate",  # Deliberately wrong; evidence wins.
            )

    async def run() -> None:
        analysis = await ManualRecordingAnalyzer(llm=_NamingLLM()).analyze(_events())  # type: ignore[arg-type]

        assert analysis.display_name == "微信公众号带图文章草稿"
        assert analysis.capability_id == "browser.submit"
        assert analysis.complete is True
        assert analysis.steps[-1]["label"].startswith("点击")
        assert any(step["parameterized"] for step in analysis.steps)
        assert "本次标题" not in str(analysis.as_dict())
        assert "本次正文" not in str(analysis.as_dict())

    asyncio.run(run())


def test_recording_analysis_exposes_incomplete_route_before_save() -> None:
    class _NamingLLM:
        async def ainvoke_structured(self, _messages, schema, **_kwargs):
            return schema(
                display_name="保存带图文章草稿",
                operation="保存带图文章草稿",
                capability_id="browser.submit",
            )

    async def run() -> None:
        analysis = await ManualRecordingAnalyzer(llm=_NamingLLM()).analyze(  # type: ignore[arg-type]
            _events(terminal=False),
        )

        assert analysis.complete is False
        assert "terminal_business_action_missing" in analysis.reasons

    asyncio.run(run())


def test_recording_analysis_rejects_a_tab_that_was_not_recordable() -> None:
    class _NamingLLM:
        async def ainvoke_structured(self, _messages, schema, **_kwargs):
            return schema(
                display_name="保存文章草稿",
                operation="保存文章草稿",
                capability_id="browser.submit",
            )

    events = _events()
    events.insert(-1, {
        "recording_id": "r1",
        "sequence": 5,
        "type": "recording_target_unavailable",
        "url": "https://cms.example.test/editor",
    })

    async def run() -> None:
        analysis = await ManualRecordingAnalyzer(llm=_NamingLLM()).analyze(events)  # type: ignore[arg-type]

        assert analysis.complete is False
        assert "recording_target_unavailable" in analysis.reasons

    asyncio.run(run())


def test_manual_recording_does_not_report_success_when_persistence_fails() -> None:
    async def run() -> None:
        cache = BrowserWorkflowCacheService(repository=_FailingRepo())  # type: ignore[arg-type]
        accepted, _reason = await capture_manual_recording(
            cache=cache,
            user_id="u1",
            main_id="m1",
            recording_id="r1",
            operation="保存带图片的文章草稿",
            events=_events(),
        )
        assert accepted is False

    asyncio.run(run())


def test_recording_journal_is_user_scoped_and_purgeable(monkeypatch) -> None:
    def unavailable_db():
        raise RuntimeError("db unavailable")

    monkeypatch.setattr("app.enterprise_capabilities.browser.engine.recording.store.get_db", unavailable_db)

    async def run() -> None:
        store = HumanRecordingStore()
        await store.append({
            "recording_id": "shared", "sequence": 1, "type": "click", "user_id": "u1",
        })
        assert len(await store.list("shared", user_id="u1")) == 1
        assert await store.list("shared", user_id="u2") == []
        await store.purge("shared", user_id="u1")
        assert await store.list("shared", user_id="u1") == []

    asyncio.run(run())


def test_recording_reservation_prevents_overwriting_active_assistance(monkeypatch) -> None:
    async def no_store(_payload):
        return None

    monkeypatch.setattr(
        "app.enterprise_capabilities.browser.engine.recording.human_recording_store.append", no_store,
    )

    async def run() -> None:
        sent = []

        async def send(frame):
            sent.append(frame)

        registry = AgentRegistry()
        await registry.attach("u1", send, [])
        assert await registry.send_command(
            "u1", "recording_start", session_id="s1", recording_id="assist-1",
        ) is True
        assert await registry.send_command(
            "u1", "recording_start", session_id="s1", recording_id="manual-2",
        ) is False
        assert await registry.send_command(
            "u1", "recording_start", session_id="s2", recording_id="manual-3",
        ) is True
        assert len(sent) == 2

    asyncio.run(run())
