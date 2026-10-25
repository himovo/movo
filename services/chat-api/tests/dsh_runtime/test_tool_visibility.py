from __future__ import annotations

import asyncio

from app.dsh_runtime.model_gateway.tool_visibility import visible_tools


TOOLS = [
    {"name": "knowledge_search"},
    {"name": "knowledge_read_document"},
    {"name": "run_script"},
    {"name": "web_search"},
]


def test_automatic_mode_keeps_tools_regardless_of_question_wording() -> None:
    for question in ("申请条件？", "请根据《制度.pdf》回答", "仅基于内部知识回答"):
        result = asyncio.run(visible_tools(
            TOOLS, session_id="session", tenant_id="tenant",
            messages=[{"role": "user", "content": question}],
        ))
        assert result == TOOLS


def test_server_selected_internal_mode_limits_tools_for_any_question() -> None:
    for question in ("申请条件？", "请通读所有规定", "给我生成文件"):
        result = asyncio.run(visible_tools(
            TOOLS, session_id="session", tenant_id="tenant", knowledge_only=True,
            messages=[{"role": "user", "content": question}],
        ))
        assert [tool["name"] for tool in result or []] == [
            "knowledge_search", "knowledge_read_document",
        ]


def test_internal_mode_does_not_expose_other_tools_when_search_is_absent() -> None:
    result = asyncio.run(visible_tools(
        [{"name": "run_script"}], session_id="session", tenant_id="tenant",
        knowledge_only=True,
    ))
    assert result == []
