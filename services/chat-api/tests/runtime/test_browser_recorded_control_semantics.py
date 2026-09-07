from __future__ import annotations
import asyncio
from app.enterprise_capabilities.browser.engine.workflow_cache.control_semantics import (
    infer_control_semantic,
)
from app.enterprise_capabilities.browser.engine.workflow_cache.manual_analysis import (
    ManualRecordingAnalyzer,
)


def test_control_semantics_uses_stable_selector_when_placeholder_is_dynamic() -> None:
    assert infer_control_semantic({
        "selector": "#search-input",
        "role": "textbox",
        "placeholder": "今日随机推荐词",
    }) == "search_query"
    assert infer_control_semantic({
        "selector": "#content-textarea",
        "role": "textbox",
    }) == "body"
    assert infer_control_semantic({
        "selector": "[data-testid=comment-editor]",
        "role": "textbox",
    }) == "comment"


def test_control_semantics_does_not_treat_css_body_or_research_as_business_role() -> None:
    assert infer_control_semantic({
        "selector": "body > main > input#employee-name",
        "role": "textbox",
    }, fallback_index=4) == "field_5"
    assert infer_control_semantic({
        "selector": "#research-notes",
        "role": "textbox",
    }, fallback_index=1) == "field_2"


def test_recording_fallback_names_terminal_send_outcome_before_search_prefix() -> None:
    class _UnavailableNamingLLM:
        async def ainvoke_structured(self, *_args, **_kwargs):
            raise RuntimeError("naming unavailable")

    home = "https://community.example.test/explore"
    results = "https://community.example.test/search?q=agents"
    detail = "https://community.example.test/posts/1"
    events = [
        {"sequence": 0, "type": "recording_started", "url": "about:blank"},
        {"sequence": 1, "type": "navigate", "before_url": "about:blank", "after_url": home, "before_fingerprint": "blank", "after_fingerprint": "home"},
        {"sequence": 2, "type": "fill", "value": "agents", "target": {"selector": "#search-input", "role": "textbox", "placeholder": "random trend"}, "before_url": home, "after_url": home, "before_fingerprint": "home", "after_fingerprint": "query"},
        {"sequence": 3, "type": "press", "key": "Enter", "target": {"selector": "#search-input", "role": "textbox"}, "before_url": home, "after_url": results, "before_fingerprint": "query", "after_fingerprint": "results"},
        {"sequence": 4, "type": "click", "target": {"role": "link", "name": "Agent patterns"}, "before_url": results, "after_url": detail, "before_fingerprint": "results", "after_fingerprint": "detail"},
        {"sequence": 5, "type": "fill", "value": "Useful note", "target": {"selector": "#comment-editor", "role": "textbox"}, "before_url": detail, "after_url": detail, "before_fingerprint": "detail", "after_fingerprint": "draft"},
        {"sequence": 6, "type": "click", "target": {"role": "button", "name": "发送", "semanticPurpose": "submit"}, "before_url": detail, "after_url": detail, "before_fingerprint": "draft", "after_fingerprint": "sent"},
        {"sequence": 7, "type": "recording_stopped", "url": detail},
    ]

    analysis = asyncio.run(
        ManualRecordingAnalyzer(llm=_UnavailableNamingLLM()).analyze(events)  # type: ignore[arg-type]
    )

    assert analysis.complete is True
    assert analysis.display_name == "community.example.test 发表评论"
    assert analysis.capability_id == "browser.submit"
