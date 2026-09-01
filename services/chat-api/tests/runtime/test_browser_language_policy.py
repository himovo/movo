from __future__ import annotations

from types import SimpleNamespace

from app.enterprise_capabilities.browser.engine.desktop_agent_executor import (
    _detect_language,
    _effect_timeline_message,
)
from app.enterprise_capabilities.browser.engine.agent_loop.planner import _decision_from_mapping


def _inputs(*, language="", messages=None, raw_messages=None, intent=""):
    return SimpleNamespace(
        language=language,
        messages=list(messages or []),
        raw_messages=list(raw_messages or []),
        intent=intent,
    )


def test_explicit_browser_language_wins_even_when_messages_are_empty() -> None:
    assert _detect_language(_inputs(language="zh-CN")) == "zh"
    assert _detect_language(_inputs(language="en-US", intent="请打开网页")) == "en"


def test_browser_language_falls_back_to_raw_user_content_and_intent() -> None:
    assert _detect_language(_inputs(
        raw_messages=[{"role": "user", "content": "请搜索 AskBot"}],
    )) == "zh"
    assert _detect_language(_inputs(intent="请搜索 AskBot")) == "zh"
    assert _detect_language(_inputs(intent="Search for AskBot")) == "en"


def test_model_and_system_rationales_keep_distinct_provenance() -> None:
    model_decision = _decision_from_mapping({
        "tool": "browser_fill",
        "args": {"text": "AskBot"},
        "rationale": "在搜索框输入 AskBot",
    })
    assert model_decision.rationale_source == "model"


def test_effect_status_is_localized_without_leaking_english_diagnostics() -> None:
    assert _effect_timeline_message(
        "confirmed_success",
        "The route changed from the homepage to results",
        lang="zh",
    ) == "操作结果：已确认成功"
    assert _effect_timeline_message(
        "confirmed_failure",
        "页面没有发生变化",
        lang="zh",
    ) == "操作结果：已确认失败（页面没有发生变化）"
