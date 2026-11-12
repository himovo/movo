"""MOVO enterprise tool calls currently do not require per-call approval."""

from __future__ import annotations


UNAPPROVED_CAPABILITIES = frozenset({
    "data.run_script@v1",
    "document.fill_form@v1",
    "browser.task@v1",
})


def skips_enterprise_approval(*, source_type: str, capability_ref: str = "") -> bool:
    return source_type in {"http", "mcp"} or (
        source_type == "internal" and capability_ref in UNAPPROVED_CAPABILITIES
    )
