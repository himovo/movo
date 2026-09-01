from app.browser.tool_deadlines import timeout_for_tool


def test_verified_mutations_leave_room_after_automatic_handoff() -> None:
    assert timeout_for_tool("browser_click") == 75.0
    assert timeout_for_tool("browser_fill") == 75.0
    assert timeout_for_tool("browser_navigate") == 75.0


def test_read_only_tools_keep_the_short_default_deadline() -> None:
    assert timeout_for_tool("browser_observe") == 60.0
    assert timeout_for_tool("browser_read_text") == 60.0
