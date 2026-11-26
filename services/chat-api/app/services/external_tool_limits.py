from __future__ import annotations

from typing import Any, Iterable, Mapping


def safe_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def enabled_mcp_tool_names(config: Mapping[str, Any] | None) -> list[str]:
    names: dict[str, None] = {}
    for item in safe_list(safe_dict(config).get("enabledToolNames")):
        name = str(item or "").strip()
        if name:
            names[name] = None
    return list(names)


def discovered_mcp_tool_count(tools: Iterable[Any] | None) -> int:
    return len([item for item in safe_list(tools) if isinstance(item, dict) and str(item.get("name") or "").strip()])


def validate_mcp_activation(*, tool_type: str, status: str, config: Mapping[str, Any] | None) -> None:
    if str(tool_type or "").strip().lower() != "mcp":
        return
    if str(status or "").strip().lower() != "active":
        return
    names = enabled_mcp_tool_names(config)
    if not names:
        raise ValueError("Please select at least one MCP tool for the Agent.")
