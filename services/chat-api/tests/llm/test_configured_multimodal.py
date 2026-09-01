from __future__ import annotations

import asyncio

import pytest

from app.infrastructure.request_context import reset_request_context, set_request_context
from app.llm.configured_models import ModelConfigError
from app.llm.configured_multimodal import ConfiguredMultimodalClient
from app.llm.types import LLMResponse, Message, Role


class _FakeClient:
    def __init__(self) -> None:
        self.messages = None

    async def ainvoke(self, messages):
        self.messages = messages
        return LLMResponse(
            message=Message(role=Role.ASSISTANT, content='{"ok": true}'),
            raw_response={"id": "response-a"},
            usage={"total_tokens": 7},
        )


def test_multimodal_client_uses_request_scoped_vision_model(monkeypatch) -> None:
    from app.llm import configured_multimodal as module

    fake = _FakeClient()
    captured = {}

    def build(config, **kwargs):
        captured["config"] = config
        captured["kwargs"] = kwargs
        return fake

    monkeypatch.setattr(module, "build_llm_client_from_config", build)
    previous = set_request_context({
        "vision_model_config": {
            "id": "vision-a",
            "model_name": "vision-model",
            "capabilities": ["vision"],
        }
    })
    try:
        result = asyncio.run(ConfiguredMultimodalClient().call_json(
            prompt="describe",
            image_bytes=b"png",
            stage="presentation_visual",
        ))
    finally:
        reset_request_context(previous)

    assert result == {"ok": True}
    assert captured["config"]["id"] == "vision-a"
    assert captured["kwargs"]["stage"] == "presentation_visual"
    content = fake.messages[0].content
    assert content[0]["type"] == "image_url"
    assert content[1] == {"type": "text", "text": "describe"}


def test_multimodal_client_fails_without_configured_vision_model() -> None:
    previous = set_request_context({})
    try:
        with pytest.raises(ModelConfigError, match="视觉模型"):
            asyncio.run(ConfiguredMultimodalClient().call(prompt="describe"))
    finally:
        reset_request_context(previous)
