"""Separate declared plugin capabilities from their on-demand execution."""

from collections.abc import Mapping

RESERVED_TOOL_NAMES = frozenset("""
    bash read write edit glob grep job_output job_list job_kill skill
    ask_user_question web_search web_fetch read_image present todo_write get_goal
    create_goal update_goal send_message interrupt_agent list_agents workflow ralph
    exit_plan_mode subagent subagent_fork run_code
""".split())


def deferred_tool_contracts(capabilities: Mapping, names: list, requirements: Mapping) -> list:
    """Publish only verified unique contracts; never load a plugin to fill gaps during chat."""
    contracts = capabilities.get("toolContracts") or []
    result = []
    for name in names:
        if name in RESERVED_TOOL_NAMES:
            continue
        matches = [item for item in contracts if isinstance(item, dict) and item.get("name") == name]
        if len(matches) == 1 and isinstance(matches[0].get("description"), str) and isinstance(matches[0].get("schema"), dict):
            result.append(matches[0])
    return result
