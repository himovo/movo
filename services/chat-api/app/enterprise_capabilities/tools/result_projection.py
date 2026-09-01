"""Canonicalize enterprise tool results before returning them to DSH."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def canonical_tool_result(receipt_result: dict[str, Any]) -> Any:
    """Return the value that matches the Tool Profile output schema.

    MCP CallToolResult wraps schema-governed data in ``structuredContent``.
    DSH validates the value returned by its Tool implementation directly, so
    forwarding the transport wrapper would incorrectly move schema properties
    one level down.
    """
    raw = receipt_result.get("raw")
    if isinstance(raw, dict):
        if "structuredContent" in raw:
            return deepcopy(raw["structuredContent"])
        return deepcopy(raw)
    return deepcopy(receipt_result)
