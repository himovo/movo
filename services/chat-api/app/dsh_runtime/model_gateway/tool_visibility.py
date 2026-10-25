"""Expose tools according to the server-selected turn mode."""

from __future__ import annotations

from typing import Any

async def visible_tools(
    tools: list[dict[str, Any]] | None,
    *,
    session_id: str,
    tenant_id: str,
    messages: list[dict[str, Any]] | None = None,
    knowledge_only: bool = False,
) -> list[dict[str, Any]] | None:
    if not tools:
        return tools
    del session_id, tenant_id, messages
    if knowledge_only:
        return [tool for tool in tools if tool.get("name") in {"knowledge_search", "knowledge_read_document"}]
    return list(tools)


__all__ = ["visible_tools"]
