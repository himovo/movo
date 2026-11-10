"""Classify the conversation capabilities exposed by an installed DSH bundle."""

from __future__ import annotations


def classify_conversation_tools(discovered: set[str], exposed: set[str]) -> tuple[str, str]:
    if not discovered:
        return "runtime_active", "no_conversation_tools"
    if discovered <= exposed:
        return "session_exposed", "invocation_not_verified"
    return "not_exposed", "tools_missing_from_session"
