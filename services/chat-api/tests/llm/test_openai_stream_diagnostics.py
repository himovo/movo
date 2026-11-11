from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

from app.llm.providers.default_openai import DefaultOpenAIClient
from app.llm.types import Message, Role


def test_stream_logs_provider_tool_metadata_without_arguments(caplog):
    caplog.set_level(logging.INFO, logger="app.llm.providers.default_openai")
    client = DefaultOpenAIClient(api_key="test-key", model="test-model")
    private_argument = "private-diagnostic-value"

    async def chunks():
        yield SimpleNamespace(
            choices=[SimpleNamespace(
                finish_reason=None,
                delta=SimpleNamespace(role="assistant", content=None, tool_calls=[
                    SimpleNamespace(index=0, id="call-1", function=SimpleNamespace(
                        name="lookup", arguments='{"value":"' + private_argument + '"}',
                    )),
                ]),
            )],
            usage=None,
            model_dump=lambda: {},
        )
        yield SimpleNamespace(
            choices=[SimpleNamespace(
                finish_reason="tool_calls",
                delta=SimpleNamespace(role=None, content=None, tool_calls=None),
            )],
            usage=None,
            model_dump=lambda: {},
        )

    async def create(**_kwargs):
        return chunks()

    client.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    async def run():
        return [chunk async for chunk in client.astream([Message(role=Role.USER, content="test")],
                                                       tools=[{"type": "function"}], tool_choice="auto")]

    result = asyncio.run(run())
    assert len(result) == 1
    assert "provider_tool_fragment_count=1" in caplog.text
    assert "finish_reason=tool_calls" in caplog.text
    assert private_argument not in caplog.text
