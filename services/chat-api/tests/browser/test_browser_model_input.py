from __future__ import annotations

import asyncio
from typing import Any

from app.llm.configured_models import reset_configured_model_context, set_configured_model_context
from app.llm.types import LLMResponse, Message, Role
from app.enterprise_capabilities.browser.engine.agent_loop.model_input import build_browser_model_input
from app.enterprise_capabilities.browser.engine.agent_loop.planner import Planner
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


def test_text_model_does_not_receive_browser_screenshot():
    result = build_browser_model_input(
        "compact DOM",
        "base64-image",
        model_config={"capabilities": ["chat"]},
    )

    assert result.content == "compact DOM"
    assert result.includes_screenshot is False


def test_vision_model_receives_browser_screenshot():
    result = build_browser_model_input(
        "compact DOM",
        "base64-image",
        model_config={"capabilities": ["chat", "vision"]},
    )

    assert result.includes_screenshot is True
    assert result.content[0] == {"type": "text", "text": "compact DOM"}
    assert result.content[1]["type"] == "image_url"


class _RejectingVisionClient:
    def __init__(self) -> None:
        self.plain_calls: list[list[Message]] = []

    async def ainvoke_structured(self, _messages, _schema, **_kwargs):
        raise ValueError("structured output unavailable")

    async def ainvoke(self, messages: list[Message], **_kwargs: Any) -> LLMResponse:
        self.plain_calls.append(messages)
        if isinstance(messages[-1].content, list):
            raise ValueError("unknown variant image_url, expected text")
        return LLMResponse(
            message=Message(
                role=Role.ASSISTANT,
                content='{"tool":"browser_done","args":{"summary":"done"},"rationale":"ok"}',
            )
        )


def test_planner_downgrades_to_dom_when_vision_payload_is_rejected():
    client = _RejectingVisionClient()
    planner = Planner()
    planner._llm = client
    previous = set_configured_model_context({"capabilities": ["chat", "vision"]})
    try:
        decision = asyncio.run(
            planner.next_step(
                "finish the task",
                [],
                Observation(
                    url="https://example.test",
                    title="Example",
                    elements=[],
                    page_text="Submit",
                    screenshot="base64-image",
                ),
            )
        )
    finally:
        reset_configured_model_context(previous)

    assert decision.tool == "browser_done"
    assert len(client.plain_calls) == 2
    assert isinstance(client.plain_calls[0][-1].content, list)
    assert isinstance(client.plain_calls[1][-1].content, str)
