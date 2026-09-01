"""Deterministic, least-privilege scopes for session approval grants."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from app.dsh_runtime.profile.tools import ToolProfileDefinition


@dataclass(frozen=True)
class ApprovalScope:
    key: str
    label: str


def approval_scope(tool: ToolProfileDefinition, arguments: dict[str, Any]) -> ApprovalScope:
    dimensions: dict[str, str] = {}
    argument_name = str(tool.approval_argument or "").strip()
    if argument_name:
        dimensions[argument_name] = str(arguments.get(argument_name) or "")
    canonical = {
        "tool_version": tool.version,
        "tool_name": tool.name,
        "approval_dimensions": dimensions,
    }
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    suffix = ", ".join(f"{name}={value}" for name, value in dimensions.items() if value)
    return ApprovalScope(
        key=hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        label=f"{tool.display_name or tool.name}{f' ({suffix})' if suffix else ''}",
    )
