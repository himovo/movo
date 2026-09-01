from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from typing import Any

import pytest

from app.dsh_runtime.model_gateway.service import (
    ModelGatewayFailure,
    ModelGatewayRequest,
    ModelGatewayService,
)
from app.dsh_runtime.model_gateway.token import ModelGatewayTokenService
from app.dsh_runtime.profile import (
    InMemoryRuntimeProfileStore,
    ModelProfileCompiler,
    RuntimeProfileResolver,
    RuntimeProfileBundle,
    RuntimeProfilePublisher,
)
from app.llm.base import BaseLLMClient
from app.llm.types import LLMResponse, Message, Role


class FakeCatalog:
    def __init__(self) -> None:
        self.instances = {
            "model-a": {
                "_id": "model-a",
                "main_id": "tenant-a",
                "provider_id": "provider-a",
                "model_name": "deepseek-chat",
                "display_name": "Default A",
                "status": "active",
                "capabilities": ["chat", "tools"],
                "max_context_tokens": 64_000,
                "settings": {"max_output_tokens": 4096},
            },
            "model-b": {
                "_id": "model-b",
                "main_id": "tenant-a",
                "provider_id": "provider-a",
                "model_name": "deepseek-reasoner",
                "display_name": "Explicit B",
                "status": "active",
                "capabilities": ["chat", "reasoning"],
                "settings": {"max_output_tokens": 8192},
            },
            "model-foreign": {
                "_id": "model-foreign",
                "main_id": "tenant-b",
                "provider_id": "provider-a",
                "model_name": "forbidden",
                "status": "active",
                "capabilities": ["chat"],
            },
        }
        self.provider = {
            "_id": "provider-a",
            "name": "ASKAI managed provider",
            "provider_type": "openai_compatible",
            "status": "active",
            "api_key": "LONG-LIVED-SECRET-MUST-NOT-LEAK",
        }

    async def resolve(self, tenant_id: str, model_instance_id: str | None):
        selected = model_instance_id or "model-a"
        return deepcopy(self.instances[selected]), deepcopy(self.provider)


class FakeClient(BaseLLMClient):
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure
        self.calls: list[tuple[list[Message], dict[str, Any]]] = []

    async def ainvoke(self, messages: list[Message], **kwargs: Any) -> LLMResponse:
        if self.failure is not None:
            raise self.failure
        self.calls.append((messages, kwargs))
        return LLMResponse(
            message=Message(role=Role.ASSISTANT, content="configured model answer"),
            usage={"prompt_tokens": 11, "completion_tokens": 7},
        )

    async def astream(self, messages: list[Message], **kwargs: Any):
        self.calls.append((messages, kwargs))
        yield LLMResponse(message=Message(role=Role.ASSISTANT, content="configured "))
        yield LLMResponse(
            message=Message(role=Role.ASSISTANT, content="model answer"),
            usage={"prompt_tokens": 11, "completion_tokens": 7},
        )

    async def ainvoke_structured(self, messages: list[Message], schema: Any, **kwargs: Any):
        raise NotImplementedError


def test_profile_compile_publish_rollback_disable_and_secret_exclusion() -> None:
    asyncio.run(_test_profile_compile_publish_rollback_disable_and_secret_exclusion())


async def _test_profile_compile_publish_rollback_disable_and_secret_exclusion() -> None:
    catalog = FakeCatalog()
    compiler = ModelProfileCompiler(catalog)
    first = await compiler.compile(tenant_id="tenant-a")
    repeated = await compiler.compile(tenant_id="tenant-a")
    assert repeated == first
    assert first.tool_versions == first.skill_versions == first.workflow_versions == first.plugin_versions == ()
    assert "LONG-LIVED-SECRET" not in first.model_dump_json()
    assert RuntimeProfileBundle.load(RuntimeProfileBundle.export(first)) == first
    tampered = json.loads(RuntimeProfileBundle.export(first))
    tampered["model_name"] = "tampered"
    with pytest.raises(ValueError, match="integrity"):
        RuntimeProfileBundle.load(json.dumps(tampered))

    store = InMemoryRuntimeProfileStore()
    publisher = RuntimeProfilePublisher(compiler, store)
    published = await publisher.publish_model_profile(tenant_id="tenant-a", actor_id="admin-1")
    assert published == first
    catalog.instances["model-a"]["display_name"] = "changed draft"
    changed = await compiler.compile(tenant_id="tenant-a")
    assert changed.profile_version != first.profile_version
    assert (await store.active("tenant-a")) == first

    second = await compiler.compile(tenant_id="tenant-a", model_instance_id="model-b")
    await store.publish(second, actor_id="admin-1")
    assert (await store.active("tenant-a")) == second
    await store.rollback("tenant-a", first.profile_version, actor_id="admin-2")
    assert (await store.active("tenant-a")) == first
    await store.disable(first.profile_version, actor_id="admin-2")
    with pytest.raises(ValueError, match="disabled"):
        await store.get(first.profile_version)
    assert [entry["action"] for entry in store.audit] == ["publish", "publish", "rollback", "disable"]


def test_profile_rejects_cross_tenant_and_resolver_scopes_ephemeral_token() -> None:
    asyncio.run(_test_profile_rejects_cross_tenant_and_resolver_scopes_ephemeral_token())


async def _test_profile_rejects_cross_tenant_and_resolver_scopes_ephemeral_token() -> None:
    compiler = ModelProfileCompiler(FakeCatalog())
    with pytest.raises(ValueError, match="cross-tenant"):
        await compiler.compile(tenant_id="tenant-a", model_instance_id="model-foreign")

    snapshot = await compiler.compile(tenant_id="tenant-a")
    store = InMemoryRuntimeProfileStore()
    await store.publish(snapshot, actor_id="admin")
    tokens = ModelGatewayTokenService("step-3-test-signing-secret")
    resolver = RuntimeProfileResolver(store, tokens, gateway_url="http://127.0.0.1/internal/dsh/model/generate")
    payload = await resolver.resolve(snapshot.profile_version, tenant_id="tenant-a")
    claims = tokens.verify(str(payload["accessToken"]))
    assert claims.tenant_id == "tenant-a"
    assert claims.model_instance_id == "model-a"
    assert payload["modelInstanceId"] == "model-a"
    assert "LONG-LIVED-SECRET" not in json.dumps(payload)
    with pytest.raises(ValueError, match="cross-tenant"):
        await resolver.resolve(snapshot.profile_version, tenant_id="tenant-b")


def test_model_gateway_enforces_scope_maps_messages_and_usage() -> None:
    asyncio.run(_test_model_gateway_enforces_scope_maps_messages_and_usage())


async def _test_model_gateway_enforces_scope_maps_messages_and_usage() -> None:
    client = FakeClient()

    async def factory(model_instance_id: str, tenant_id: str, _request: ModelGatewayRequest) -> BaseLLMClient:
        assert (model_instance_id, tenant_id) == ("model-a", "tenant-a")
        return client

    token_service = ModelGatewayTokenService("step-3-test-signing-secret")
    claims = token_service.verify(
        token_service.issue(tenant_id="tenant-a", profile_version="profile-a", model_instance_id="model-a")
    )
    request = ModelGatewayRequest(
        profileVersion="profile-a",
        modelInstanceId="model-a",
        provider="askai-model-gateway",
        model="deepseek-chat",
        system="enterprise system",
        messages=[{"role": "user", "content": [{"type": "text", "text": "hello"}]}],
        maxTokens=123,
    )
    response = await ModelGatewayService(factory).generate(request, claims)
    assert response.text == "configured model answer"
    assert response.usage == {"inputTokens": 11, "outputTokens": 7}
    assert [message.role for message in client.calls[0][0]] == [Role.SYSTEM, Role.USER]
    assert client.calls[0][1]["max_tokens"] == 123

    async def collect_stream():
        stream = await ModelGatewayService(factory).stream(request, claims)
        return [event async for event in stream]

    events = await collect_stream()
    assert [event["type"] for event in events] == ["text-delta", "text-delta", "usage", "finish"]
    assert "".join(event.get("text", "") for event in events) == "configured model answer"

    wrong_model = request.model_copy(update={"modelInstanceId": "model-b"})
    with pytest.raises(ModelGatewayFailure, match="model scope mismatch"):
        await ModelGatewayService(factory).generate(wrong_model, claims)


@pytest.mark.parametrize(
    ("provider_error", "expected_code", "retryable"),
    [
        (RuntimeError("401 invalid API key"), "model_authentication_failed", False),
        (RuntimeError("429 rate limit"), "model_rate_limited", True),
        (RuntimeError("insufficient quota"), "model_quota_exhausted", False),
        (TimeoutError("timed out"), "model_timeout", True),
    ],
)
def test_model_gateway_normalizes_provider_failures(
    provider_error: Exception,
    expected_code: str,
    retryable: bool,
) -> None:
    async def run() -> None:
        async def factory(_model: str, _tenant: str, _request: ModelGatewayRequest) -> BaseLLMClient:
            return FakeClient(failure=provider_error)

        tokens = ModelGatewayTokenService("step-3-test-signing-secret")
        claims = tokens.verify(
            tokens.issue(tenant_id="tenant-a", profile_version="profile-a", model_instance_id="model-a")
        )
        request = ModelGatewayRequest(
            profileVersion="profile-a",
            modelInstanceId="model-a",
            provider="askai-model-gateway",
            model="deepseek-chat",
            messages=[{"role": "user", "content": "hello"}],
        )
        with pytest.raises(ModelGatewayFailure) as captured:
            await ModelGatewayService(factory).generate(request, claims)
        assert captured.value.code == expected_code
        assert captured.value.retryable is retryable

    asyncio.run(run())


def test_model_gateway_redacts_provider_secrets() -> None:
    message = ModelGatewayService._safe_message(RuntimeError("API key=sk-1234567890SECRET rejected"))
    assert "1234567890SECRET" not in message
    assert "[REDACTED]" in message
