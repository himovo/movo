from app.dsh_runtime.locale import resolve_turn_locale


def test_turn_locale_follows_explicit_user_setting_then_message_language() -> None:
    assert resolve_turn_locale("请搜索 AskBot") == "zh-CN"
    assert resolve_turn_locale("Search for AskBot") == "en-US"
    assert resolve_turn_locale("请搜索 AskBot", explicit="en-US") == "en-US"
    assert resolve_turn_locale("Search for AskBot", explicit="zh_CN") == "zh-CN"
