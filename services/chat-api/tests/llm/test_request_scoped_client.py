from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, List, Type

from pydantic import BaseModel

from app.llm.base import BaseLLMClient
from app.llm.configured_models import reset_configured_model_context, set_configured_model_context
from app.llm.factory import get_request_scoped_llm_client
from app.llm.types import LLMResponse, Message, Role
from app.llm.request_scoped_client import RequestScopedLLMClient


class _StructuredResult(BaseModel):
    model: str = ""


class _FakeClient(BaseLLMClient):
    def __init__(self, model: str):
        self.model = model
        self.calls: List[dict[str, Any]] = []

    async def ainvoke(self, messages: List[Message], **kwargs: Any) -> LLMResponse:
        await asyncio.sleep(0)
        self.calls.append(dict(kwargs))
        return LLMResponse(message=Message(role=Role.ASSISTANT, content=self.model))

    async def astream(self, messages: List[Message], **kwargs: Any) -> AsyncGenerator[LLMResponse, None]:
        self.calls.append(dict(kwargs))
        yield LLMResponse(message=Message(role=Role.ASSISTANT, content=f"{self.model}:1"))
        await asyncio.sleep(0)
        yield LLMResponse(message=Message(role=Role.ASSISTANT, content=f"{self.model}:2"))

    async def ainvoke_structured(
        self,
        messages: List[Message],
        schema: Type[BaseModel],
        **kwargs: Any,
    ) -> BaseModel:
        await asyncio.sleep(0)
        self.calls.append(dict(kwargs))
        return schema(model=self.model)


def _configured_model(name: str) -> dict[str, Any]:
    return {
        "id": f"id-{name}",
        "provider_type": "openai_compatible",
        "provider_name": name,
        "api_key": "test-key",
        "base_url": f"https://{name}.example.test/v1",
        "model_name": name,
        "structured_output_mode": "prompt_json",
    }


def test_same_proxy_resolves_each_concurrent_request_model(monkeypatch):
    created: List[_FakeClient] = []

    def fake_build(config, **_kwargs):
        client = _FakeClient(str(config.get("model_name") or ""))
        created.append(client)
        return client

    monkeypatch.setattr("app.llm.factory.build_llm_client_from_config", fake_build)
    proxy = get_request_scoped_llm_client(streaming=False, stage="compose", intent="generation")
    messages = [Message(role=Role.USER, content="test")]

    async def invoke_for(model: str) -> str:
        previous = set_configured_model_context(_configured_model(model))
        try:
            await asyncio.sleep(0)
            response = await proxy.ainvoke(messages)
            return str(response.content)
        finally:
            reset_configured_model_context(previous)

    async def run():
        return await asyncio.gather(
            invoke_for("deepseek-v4-flash"),
            invoke_for("qwen-plus"),
        )

    assert asyncio.run(run()) == ["deepseek-v4-flash", "qwen-plus"]
    assert sorted(client.model for client in created) == ["deepseek-v4-flash", "qwen-plus"]


def test_structured_output_uses_current_request_model(monkeypatch):
    monkeypatch.setattr(
        "app.llm.factory.build_llm_client_from_config",
        lambda config, **_kwargs: _FakeClient(str(config.get("model_name") or "")),
    )
    proxy = get_request_scoped_llm_client(streaming=False, stage="planning")
    previous = set_configured_model_context(_configured_model("deepseek-v4-flash"))
    try:
        result = asyncio.run(
            proxy.with_structured_output(_StructuredResult, method="function_calling").ainvoke(
                [Message(role=Role.USER, content="structured")]
            )
        )
    finally:
        reset_configured_model_context(previous)

    assert result.model == "deepseek-v4-flash"


def test_stream_resolves_provider_once(monkeypatch):
    build_count = 0

    def fake_build(config, **_kwargs):
        nonlocal build_count
        build_count += 1
        return _FakeClient(str(config.get("model_name") or ""))

    monkeypatch.setattr("app.llm.factory.build_llm_client_from_config", fake_build)
    proxy = get_request_scoped_llm_client(streaming=True, stage="compose")

    async def run():
        previous = set_configured_model_context(_configured_model("deepseek-v4-flash"))
        try:
            return [chunk.content async for chunk in proxy.astream([Message(role=Role.USER, content="stream")])]
        finally:
            reset_configured_model_context(previous)

    assert asyncio.run(run()) == ["deepseek-v4-flash:1", "deepseek-v4-flash:2"]
    assert build_count == 1


def test_tool_binding_is_forwarded_to_resolved_client(monkeypatch):
    client = _FakeClient("deepseek-v4-flash")
    monkeypatch.setattr("app.llm.factory.build_llm_client_from_config", lambda *_args, **_kwargs: client)

    class Tool:
        name = "lookup"
        description = "Lookup data"
        args_schema = None

    proxy = get_request_scoped_llm_client(streaming=False, stage="research_planning")
    bound = proxy.bind_tools([Tool()])
    previous = set_configured_model_context(_configured_model("deepseek-v4-flash"))
    try:
        asyncio.run(bound.ainvoke([Message(role=Role.USER, content="use tool")]))
    finally:
        reset_configured_model_context(previous)

    assert client.calls[0]["tool_choice"] == "auto"
    assert client.calls[0]["tools"][0]["function"]["name"] == "lookup"


def test_no_request_context_uses_factory_fallback(monkeypatch):
    fallback = _FakeClient("system-default")
    monkeypatch.setattr("app.llm.factory.get_llm_client", lambda **_kwargs: fallback)
    proxy = get_request_scoped_llm_client(streaming=False, stage="planning")

    response = asyncio.run(proxy.ainvoke([Message(role=Role.USER, content="background")]))

    assert response.content == "system-default"


def test_long_lived_runtime_components_hold_proxy_not_concrete_provider():
    from app.enterprise_capabilities.content.profile_presets.resolver import ProfilePresetResolver
    from app.enterprise_capabilities.content.publish_assembly.deferred_finalizer import DeferredVisualFinalizer
    from app.enterprise_capabilities.content.writer_engine.pipeline import WriterEnginePipeline

    profile = ProfilePresetResolver()
    writer = WriterEnginePipeline()
    visuals = DeferredVisualFinalizer()

    assert isinstance(profile._llm, RequestScopedLLMClient)
    assert isinstance(profile._conflicts._llm, RequestScopedLLMClient)
    assert isinstance(profile._synth._llm, RequestScopedLLMClient)
    assert isinstance(writer._llm, RequestScopedLLMClient)
    assert writer._planner.deps.llm is writer._llm
    assert writer._writer.deps.llm is writer._llm
    assert writer._visual.deps.llm is writer._llm
    assert writer._single.deps.llm is writer._llm
    assert isinstance(visuals._llm, RequestScopedLLMClient)
