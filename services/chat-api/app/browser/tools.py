"""Canonical browser tool names. Kept here so backend + frontend + agent
all reference the same strings.
"""

BROWSER_TOOLS = [
    "browser_execute_workflow",
    "browser_navigate",
    "browser_observe",
    "browser_click",
    "browser_click_at",
    "browser_hover",
    "browser_fill",
    "browser_type_at",
    "browser_select",
    "browser_upload_file",
    "browser_paste_image",
    "browser_press",
    "browser_scroll",
    "browser_wait_for",
    "browser_screenshot",
    "browser_read_text",
    "browser_tab_new",
    "browser_back",
    "browser_forward",
]

# Virtual control-flow tools the ReAct loop understands internally. These
# are NOT dispatched to the agent — they terminate / redirect the loop.
CONTROL_TOOLS = [
    "browser_done",     # task finished successfully
    "browser_ask_user", # pause and ask the user
    "browser_fail",     # give up
]


def is_browser_tool(name: str) -> bool:
    return name in BROWSER_TOOLS


def is_control_tool(name: str) -> bool:
    return name in CONTROL_TOOLS
