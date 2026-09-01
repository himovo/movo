"""Browser action-contract taxonomy.

Seven capabilities cover common browser tasks — each declares a required
produce shape so the executor can validate the LLM's browser_done.data
structurally, no keywords.

Public API:
    BrowserActionSpec, ContractResult  (types)
    get_spec(capability_id)            (lookup)
    validate_data(capability_id, data) (contract check)
    list_specs()                       (registry enumeration)
    describe_for_planner(lang)         (menu shown to the planner LLM)
    describe_for_agent(cap_id, lang)   (single-cap explanation shown
                                        to the browser-task planner LLM)
"""
from __future__ import annotations

from .schema import BrowserActionSpec, ContractResult
from .registry import (
    blocks_whole_node_replay,
    describe_for_agent,
    describe_for_planner,
    get_spec,
    list_specs,
    validate_data,
)

__all__ = [
    "BrowserActionSpec",
    "ContractResult",
    "blocks_whole_node_replay",
    "describe_for_agent",
    "describe_for_planner",
    "get_spec",
    "list_specs",
    "validate_data",
]
