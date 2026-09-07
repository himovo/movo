from types import SimpleNamespace

from app.enterprise_capabilities.browser.engine.agent_loop.decision_diagnostics import summarize_actions


def test_search_value_is_logged_for_search_field() -> None:
    result = summarize_actions(
        [SimpleNamespace(tool="browser_fill", args={"ref": "e1", "value": "MOVO 官网"})],
        [{"ref": "e1", "role": "textbox", "name": "搜索", "searchContext": True}],
    )

    assert result[0]["search_value"] == "MOVO 官网"


def test_searchbox_role_is_enough_to_log_search_value() -> None:
    result = summarize_actions(
        [SimpleNamespace(
            tool="browser_fill",
            args={"ref": "search", "value": "Deepseek Harness"},
        )],
        [{"ref": "search", "role": "searchbox", "name": "动态热词"}],
    )

    assert result[0]["search_value"] == "Deepseek Harness"


def test_non_search_form_value_is_not_logged() -> None:
    result = summarize_actions(
        [SimpleNamespace(tool="browser_fill", args={"ref": "e2", "value": "secret"})],
        [{"ref": "e2", "role": "textbox", "name": "密码", "searchContext": False}],
    )

    assert "search_value" not in result[0]
