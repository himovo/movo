"""Backward-compatible alias — crud_rules was the first iteration of
the rule layer. The canonical home is now ``app.enterprise_capabilities.browser.engine.rules``.
This module re-exports the CRUD-relevant surface so existing imports
keep working; new code should import from ``rules`` directly.
"""
from app.enterprise_capabilities.browser.engine.rules import (
    AUTO_EXECUTE, LLM_PICK, FALLBACK, SKIP,
    CandidateSet,
    matchers, tokens,
)
from app.enterprise_capabilities.browser.engine.rules.crud import (
    find_create as find_create_entries,
    find_read as find_read_action,
    find_update as find_update_entries,
    find_delete as find_delete_entries,
    find_confirm as find_confirm_button,
    resolve,
)

__all__ = [
    "AUTO_EXECUTE", "LLM_PICK", "FALLBACK", "SKIP",
    "CandidateSet",
    "matchers", "tokens",
    "find_create_entries", "find_read_action",
    "find_update_entries", "find_delete_entries",
    "find_confirm_button",
    "resolve",
]
