from app.enterprise_capabilities.browser.engine.form_input.input_context import BrowserInputContext
from app.enterprise_capabilities.browser.engine.workflow_cache.contracts import CachedWorkflowStep
from app.enterprise_capabilities.browser.engine.workflow_cache.coverage import assess_compiled_workflow
from app.enterprise_capabilities.browser.engine.workflow_cache.manual_plan import build_manual_recording_plan
from app.enterprise_capabilities.browser.engine.workflow_cache.locator_portability import portable_locator
from app.enterprise_capabilities.browser.engine.workflow_cache.page_state import url_shape
from app.enterprise_capabilities.browser.engine.workflow_cache.url_portability import portable_navigation_url


def test_portable_url_removes_session_material_but_keeps_business_route() -> None:
    url = "https://app.example.test/editor?action=create&type=article&token=secret&timestamp=123"

    assert portable_navigation_url(url) == (
        "https://app.example.test/editor?action=create&type=article"
    )
    assert url_shape(url) == "app.example.test/editor?action&type"


def test_generic_recording_compaction_produces_value_free_causal_route() -> None:
    home = "https://app.example.test/home?section=content&session_id=secret"
    listing = "https://app.example.test/list?action=drafts&token=secret"
    editor = "https://app.example.test/editor?action=create&nonce=secret"
    events = [
        {"sequence": 0, "type": "recording_started", "url": "about:blank"},
        {"sequence": 1, "type": "navigate", "before_url": "about:blank", "after_url": home, "before_fingerprint": "a", "after_fingerprint": "b"},
        {"sequence": 2, "type": "click", "target": {"selector": "#drafts", "role": "link", "name": "草稿"}, "before_url": home, "after_url": listing, "before_fingerprint": "b", "after_fingerprint": "c"},
        # Browser lifecycle duplicate of the click outcome.
        {"sequence": 3, "type": "navigate", "before_url": listing, "after_url": listing, "before_fingerprint": "c", "after_fingerprint": "c2"},
        {"sequence": 4, "type": "click", "target": {"selector": "#create", "role": "button", "name": "新建"}, "before_url": listing, "after_url": "about:blank", "before_fingerprint": "c2", "after_fingerprint": "blank"},
        {"sequence": 5, "type": "navigate", "before_url": "about:blank", "after_url": editor, "before_fingerprint": "blank", "after_fingerprint": "d"},
        # Focus click and filled element are one replayable edit.
        {"sequence": 6, "type": "click", "target": {"selector": "body > div:nth-of-type(9)", "role": "textbox", "name": "正文"}, "before_url": editor, "after_url": editor, "before_fingerprint": "d", "after_fingerprint": "e"},
        {"sequence": 7, "type": "fill", "value": "本次动态正文", "target": {"selector": "body > div:nth-of-type(9)", "role": "textbox", "name": "本次动态正文"}, "before_url": editor, "after_url": editor, "before_fingerprint": "e", "after_fingerprint": "f"},
        # Native file click is preparation for the upload, not another step.
        {"sequence": 8, "type": "click", "target": {"selector": "body > input:nth-of-type(2)", "role": "textbox", "type": "file", "accept": "image/*"}, "before_url": editor, "after_url": editor, "before_fingerprint": "f", "after_fingerprint": "g"},
        {"sequence": 9, "type": "upload", "file_count": 1, "target": {"selector": "body > input:nth-of-type(2)", "role": "textbox", "type": "file", "accept": "image/*"}, "before_url": editor, "after_url": editor, "before_fingerprint": "g", "after_fingerprint": "h"},
        {"sequence": 10, "type": "click", "target": {"selector": "body > footer:nth-of-type(2) > button", "role": "button", "name": "保存", "semanticPurpose": "save"}, "before_url": editor, "after_url": editor, "before_fingerprint": "h", "after_fingerprint": "i"},
        {"sequence": 11, "type": "recording_stopped", "url": editor},
    ]

    plan = build_manual_recording_plan(
        events=events,
        operation="新建带图片内容并保存",
        capability_id="browser.submit",
    )

    assert plan.complete is True
    assert [step.tool for step in plan.compiled.steps] == [
        "browser_navigate", "browser_click", "browser_click",
        "browser_fill", "browser_upload_file", "browser_click",
    ]
    serialized = str([step.model_dump() for step in plan.compiled.steps])
    assert "secret" not in serialized
    assert "本次动态正文" not in serialized
    assert plan.compiled.steps[3].locator == {"role": "textbox", "name": "正文"}
    assert plan.compiled.steps[4].locator == {
        "role": "textbox", "type": "file", "accept": "image/*",
    }


def test_quality_gate_rejects_a_pure_positional_action_locator() -> None:
    result = assess_compiled_workflow(
        steps=[CachedWorkflowStep(
            tool="browser_click",
            locator={"selector": "body > div:nth-of-type(7) > span"},
        )],
        context=BrowserInputContext(original_request="打开项目", candidates=[]),
        capability_id="browser.navigate",
    )

    assert result.allowed is False
    assert result.reasons == ("unstable_recorded_locator_present",)


def test_content_scoped_link_does_not_depend_on_its_positional_selector() -> None:
    locator = portable_locator({
        "selector": "body > main > section:nth-of-type(7) > a",
        "role": "link",
        "contentContextId": "attribute:data-note-id:abc12345",
    })
    result = assess_compiled_workflow(
        steps=[CachedWorkflowStep(
            tool="browser_click",
            locator=locator,
        )],
        context=BrowserInputContext(original_request="打开目标内容", candidates=[]),
        capability_id="browser.navigate",
    )

    assert result.allowed is True
    assert result.reasons == ()
    assert "selector" not in locator


def test_search_locator_does_not_cache_rotating_placeholder_text() -> None:
    locator = portable_locator({
        "selector": "#search-input",
        "role": "textbox",
        "placeholder": "八十中高中老师",
        "scopeRole": "header",
    })

    assert locator == {
        "selector": "#search-input",
        "role": "textbox",
        "scopeRole": "header",
    }


def test_regular_form_locator_keeps_stable_placeholder_text() -> None:
    locator = portable_locator({
        "selector": "#employee-name",
        "role": "textbox",
        "placeholder": "请输入员工姓名",
    })

    assert locator["placeholder"] == "请输入员工姓名"
