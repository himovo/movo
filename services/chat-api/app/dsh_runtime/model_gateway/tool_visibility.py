"""Per-turn visibility for immutable Runtime Profile tools."""

from __future__ import annotations

from typing import Any

async def visible_tools(
    tools: list[dict[str, Any]] | None,
    *,
    session_id: str,
    tenant_id: str,
) -> list[dict[str, Any]] | None:
    """Hide tools that are unavailable in the active trusted turn.

    Runtime Profiles remain immutable. Internal knowledge search is available
    in automatic and strict retrieval modes; ASKAI still injects its governed
    tenant and knowledge-base scope when the tool executes. URL collection is
    always available through direct HTTP; Firecrawl is only an optional fallback.
    """
    if not tools:
        return tools
    del session_id, tenant_id
    return list(tools)


__all__ = ["visible_tools"]
