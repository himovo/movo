from __future__ import annotations


DEFAULT_TOOL_TIMEOUT_SECONDS = 60.0

# The sidecar may spend up to 45 seconds waiting for automatic human-to-agent
# handoff before it starts a verified mutation. These tools therefore share a
# bounded post-handoff window. Read-only calls retain the shorter default, so a
# broken DOM observation still fails fast instead of blocking the agent loop.
_VERIFIED_MUTATION_TIMEOUT_SECONDS = 75.0
_TOOL_TIMEOUTS = {
    tool: _VERIFIED_MUTATION_TIMEOUT_SECONDS
    for tool in {
        "browser_navigate",
        "browser_click",
        "browser_click_at",
        "browser_hover",
        "browser_fill",
        "browser_type_at",
        "browser_select",
        "browser_press",
        "browser_scroll",
        "browser_upload_file",
        "browser_paste_image",
        "browser_tab_new",
        "browser_back",
        "browser_forward",
    }
}


def timeout_for_tool(tool: str) -> float:
    return _TOOL_TIMEOUTS.get(str(tool or ""), DEFAULT_TOOL_TIMEOUT_SECONDS)


__all__ = ["timeout_for_tool"]
