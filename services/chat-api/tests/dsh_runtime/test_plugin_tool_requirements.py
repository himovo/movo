from app.dsh_runtime.plugin_management.tool_requirements import tool_requirements


def test_workspace_requirements_are_declarative_and_versioned() -> None:
    assert tool_requirements("dsh-office-tools", "1.0.8", ["word_create", "word_read"]) == {
        "word_create": ["workspace"],
        "word_read": ["workspace"],
    }
    assert tool_requirements("unrelated-plugin", "1.0.0", ["word_create"]) == {}
    assert tool_requirements("dsh-office-tools", "2.0.0", ["word_create"]) == {
        "word_create": ["workspace"],
    }
