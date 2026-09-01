from __future__ import annotations

import asyncio

from app.dsh_runtime.model_gateway.tool_visibility import visible_tools


def test_automatic_mode_keeps_internal_url_collection_and_both_search_depths_visible() -> None:
    tools = [
        {"name": "knowledge_search"}, {"name": "web_collect"},
        {"name": "web_search"}, {"name": "progressive_research"},
    ]
    result = asyncio.run(visible_tools(tools, session_id="session-a", tenant_id="tenant-a"))
    assert [tool["name"] for tool in result or []] == [
        "knowledge_search", "web_collect", "web_search", "progressive_research",
    ]


def test_internal_knowledge_and_collector_are_visible_without_firecrawl_configuration() -> None:
    tools = [{"name": "knowledge_search"}, {"name": "web_collect"}]
    result = asyncio.run(visible_tools(tools, session_id="session-a", tenant_id="tenant-a"))
    assert [tool["name"] for tool in result or []] == ["knowledge_search", "web_collect"]
