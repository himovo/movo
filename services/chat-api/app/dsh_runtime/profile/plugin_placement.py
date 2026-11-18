"""Plugin placement based on the verified capabilities of an installation."""

from collections.abc import Mapping

# Keep aligned with the Runtime Host policy. The contract test checks parity.
RESERVED_TOOL_NAMES = frozenset("""
    bash read write edit glob grep job_output job_list job_kill skill
    ask_user_question web_search web_fetch read_image present todo_write get_goal
    create_goal update_goal send_message interrupt_agent list_agents workflow ralph
    exit_plan_mode subagent subagent_fork run_code
""".split())


def is_standalone_ui_candidate(capabilities: Mapping, tool_names: list) -> bool:
    modules = capabilities.get("clientModules")
    if capabilities.get("runtimePlacement") != "standalone-ui-v1" or tool_names or not modules:
        return False
    if not all(isinstance(module, Mapping) and module.get("conversationView") is False for module in modules):
        return False
    # Older or incomplete assessments cannot establish the absence of a contribution.
    return all(capabilities.get(key) == [] for key in (
        "commands", "skills", "modelProviders", "mcpServers", "overrides",
    ))


def deferred_tool_contracts(capabilities: Mapping, names: list, requirements: Mapping) -> list:
    """Return complete contracts for tools without observed session contributions."""
    modules = capabilities.get("clientModules")
    if (capabilities.get("runtimePlacement") != "isolated-tool-call-v1"
            or not names or RESERVED_TOOL_NAMES.intersection(names)
            or requirements or not isinstance(modules, list)):
        return []
    if any(not isinstance(module, Mapping) or module.get("conversationView") is not False for module in modules):
        return []
    if any(capabilities.get(key) != [] for key in (
        "commands", "skills", "modelProviders", "overrides",
    )):
        return []
    if not isinstance(capabilities.get("mcpServers"), list):
        return []
    if not modules and any(capabilities.get(key) != [] for key in ("remoteEndpoints", "webRoutes")):
        return []
    contracts = capabilities.get("toolContracts")
    if not isinstance(contracts, list) or len(contracts) != len(set(names)):
        return []
    if any(not isinstance(item, dict) or not isinstance(item.get("name"), str)
           or not isinstance(item.get("description"), str) or not isinstance(item.get("schema"), dict)
           for item in contracts):
        return []
    return contracts if {item["name"] for item in contracts} == set(names) else []
