"""Compile-time checks for adaptive Workflow Skill contracts."""

from __future__ import annotations

from typing import Any

from app.dsh_runtime.profile.tools import ToolProfileDefinition


def validate_node_identity(nodes: list[dict[str, Any]]) -> None:
    _require_unique(nodes, "id", "workflow node id")
    aliases = [
        str(node.get("outputAlias") or node.get("output_alias") or "").strip()
        for node in nodes
    ]
    populated = [value for value in aliases if value]
    if len(populated) != len(set(populated)):
        raise ValueError("workflow output aliases must be unique")


def validate_external_bindings(node: dict[str, Any], tool: ToolProfileDefinition) -> None:
    config = node.get("businessConfig") if isinstance(node.get("businessConfig"), dict) else {}
    bindings = config.get("tool_arg_bindings") or config.get("toolArgBindings") or []
    if not isinstance(bindings, list):
        raise ValueError("workflow external tool bindings must be an array")
    schema = tool.input_schema if isinstance(tool.input_schema, dict) else {}
    if schema.get("type") not in {None, "object"}:
        raise ValueError(f"workflow external tool requires an object input schema: {tool.name}")
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    names: list[str] = []
    for item in bindings:
        if not isinstance(item, dict):
            raise ValueError("workflow external tool binding must be an object")
        name = str(item.get("arg_name") or item.get("argName") or item.get("name") or "").strip()
        if not name:
            raise ValueError("workflow external tool binding has no argument name")
        names.append(name)
        if name not in properties and schema.get("additionalProperties") is False:
            raise ValueError(f"workflow binding is not declared by tool schema: {tool.name}.{name}")
    if len(names) != len(set(names)):
        raise ValueError(f"workflow has duplicate bindings for external tool: {tool.name}")


def _require_unique(nodes: list[dict[str, Any]], key: str, label: str) -> None:
    values = [str(node.get(key) or "").strip() for node in nodes]
    if any(not value for value in values):
        raise ValueError(f"{label} must not be empty")
    if len(values) != len(set(values)):
        raise ValueError(f"{label}s must be unique")
