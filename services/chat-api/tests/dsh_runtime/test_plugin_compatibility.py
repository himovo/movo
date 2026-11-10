from app.dsh_runtime.plugin_management.compatibility import classify_conversation_tools


def test_bundle_without_conversation_tools_can_still_have_host_capabilities():
    assert classify_conversation_tools(set(), set()) == ("runtime_active", "no_conversation_tools")


def test_all_tools_must_be_exposed_to_the_session():
    assert classify_conversation_tools({"a", "b"}, {"a"}) == ("not_exposed", "tools_missing_from_session")
    assert classify_conversation_tools({"a", "b"}, {"a", "b"}) == ("session_exposed", "invocation_not_verified")
