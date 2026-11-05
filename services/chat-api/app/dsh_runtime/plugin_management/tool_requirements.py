"""Declarative session prerequisites for third-party plugin tools."""

from __future__ import annotations

import json
from pathlib import Path


_DECLARATIONS = json.loads(Path(__file__).with_suffix(".json").read_text(encoding="utf-8"))
_SUPPORTED = {"workspace"}


def tool_requirements(name: str, version: str, tool_names: list[str]) -> dict[str, list[str]]:
    declared = _DECLARATIONS.get(f"{name}@{version}", _DECLARATIONS.get(name, {}))
    result: dict[str, list[str]] = {}
    for tool_name in tool_names:
        requirements = declared.get(tool_name, [])
        if not isinstance(requirements, list) or any(item not in _SUPPORTED for item in requirements):
            raise ValueError(f"Invalid plugin tool requirements for {tool_name}")
        if requirements:
            result[tool_name] = requirements
    return result
