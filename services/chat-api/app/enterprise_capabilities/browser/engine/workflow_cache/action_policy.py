from __future__ import annotations

from typing import Any, Literal, Mapping


ActionDisposition = Literal["ignore", "replay", "unsupported"]


OBSERVATION_ONLY_TOOLS = frozenset({
    "browser_observe", "browser_read_text", "browser_screenshot",
    "browser_done", "browser_fail", "browser_ask_user",
})

DYNAMIC_MUTATION_TOOLS = frozenset({
    "browser_fill", "browser_type_at", "browser_select",
    "browser_upload_file", "browser_paste_image",
})

REPLAYABLE_ACTION_TOOLS = frozenset({
    "browser_navigate", "browser_tab_new", "browser_click", "browser_click_at",
    "browser_hover", "browser_fill", "browser_type_at", "browser_select",
    "browser_press", "browser_scroll", "browser_upload_file", "browser_paste_image",
    "browser_back", "browser_forward", "browser_wait_for",
})

ALWAYS_LOCATOR_REQUIRED_TOOLS = frozenset({
    "browser_click", "browser_click_at", "browser_hover", "browser_fill",
    "browser_type_at", "browser_select", "browser_upload_file", "browser_paste_image",
})


def action_disposition(tool: str) -> ActionDisposition:
    normalized = str(tool or "").strip()
    if normalized in OBSERVATION_ONLY_TOOLS or normalized.startswith("__"):
        return "ignore"
    if normalized in REPLAYABLE_ACTION_TOOLS:
        return "replay"
    return "unsupported"


def stable_locator_required(tool: str, args: Mapping[str, Any] | None = None) -> bool:
    normalized = str(tool or "").strip()
    if normalized in ALWAYS_LOCATOR_REQUIRED_TOOLS:
        return True
    values = args if isinstance(args, Mapping) else {}
    # A ref is an ephemeral DOM handle. A ref-only wait is replayable only
    # after the trace converts that handle into a semantic locator. If text is
    # also present, text remains a portable fallback and a locator is optional.
    return bool(
        normalized == "browser_wait_for"
        and str(values.get("ref") or "").strip()
        and not str(values.get("text") or "").strip()
    )


__all__ = [
    "ALWAYS_LOCATOR_REQUIRED_TOOLS",
    "DYNAMIC_MUTATION_TOOLS",
    "OBSERVATION_ONLY_TOOLS",
    "REPLAYABLE_ACTION_TOOLS",
    "ActionDisposition",
    "action_disposition",
    "stable_locator_required",
]
