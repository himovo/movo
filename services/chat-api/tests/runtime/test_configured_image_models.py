import asyncio

import pytest

from app.api.endpoints import models as model_endpoints
from app.infrastructure.request_context import reset_request_context, set_request_context
from app.services.image_generation import ConfiguredImageGenerationService
from app.llm.configured_models import ModelConfigError


def test_image_service_resolves_explicit_model_id(monkeypatch):
    service = ConfiguredImageGenerationService()
    calls = {}

    async def _fake_get_image_model_config(model_id: str, main_id: str):
        calls["model_id"] = model_id
        calls["main_id"] = main_id
        return {"id": model_id, "model_name": "gpt-image-2"}

    async def _fake_get_default_image_model_config(main_id: str):
        raise AssertionError("default image model should not be used when image_model_id is set")

    monkeypatch.setattr("app.services.image_generation.get_image_model_config", _fake_get_image_model_config)
    monkeypatch.setattr("app.services.image_generation.get_default_image_model_config", _fake_get_default_image_model_config)
    previous = set_request_context({"main_id": "tenant_ctx"})
    try:
        config, source = asyncio.run(
            service._resolve_image_model_config(
                output_spec={"image_model_id": "img_model_1"},
            )
        )
    finally:
        reset_request_context(previous)

    assert source == "admin_config"
    assert config["id"] == "img_model_1"
    assert calls == {"model_id": "img_model_1", "main_id": "tenant_ctx"}


def test_available_models_supports_capability_filter(monkeypatch):
    async def _fake_list_model_options(main_id: str, *, capability: str = "chat"):
        assert main_id == "tenant_a"
        assert capability == "image_generation"
        return [{"id": "img_a"}]

    async def _fake_list_chat_model_options(main_id: str):
        raise AssertionError("chat model options should not be called for image_generation capability")

    monkeypatch.setattr(model_endpoints, "list_model_options", _fake_list_model_options)
    monkeypatch.setattr(model_endpoints, "list_chat_model_options", _fake_list_chat_model_options)

    result = asyncio.run(model_endpoints.available_models(main_id="tenant_a", capability="image_generation"))

    assert result == {"code": 0, "data": [{"id": "img_a"}]}


def test_image_service_has_no_environment_model_fallback(monkeypatch):
    service = ConfiguredImageGenerationService()

    async def _no_default(main_id: str):
        return None

    monkeypatch.setattr("app.services.image_generation.get_default_image_model_config", _no_default)
    previous = set_request_context({"main_id": "tenant-no-image"})
    try:
        with pytest.raises(ModelConfigError, match="管理后台"):
            asyncio.run(service.generate(prompt="生成封面", user_id="user-a"))
    finally:
        reset_request_context(previous)


def test_image_model_test_uses_configured_image_model(monkeypatch):
    calls = {}

    async def _fake_generate_image_asset(**kwargs):
        calls.update(kwargs)
        return {
            "image_url": "https://example.com/generated.png",
            "object_path": "assets/generated.png",
            "request_id": "req_123",
            "model_source": "admin_config",
            "provider_type": "azure_openai",
            "runtime_kind": "azure_openai_images",
        }

    async def _fake_update_model_health(model_id: str, main_id: str, health_status: str, last_error: str = ""):
        calls["health"] = {
            "model_id": model_id,
            "main_id": main_id,
            "health_status": health_status,
            "last_error": last_error,
        }

    monkeypatch.setattr(model_endpoints, "generate_image_asset", _fake_generate_image_asset)
    monkeypatch.setattr(model_endpoints, "update_model_health", _fake_update_model_health)

    payload = model_endpoints.ImageModelTestPayload(
        prompt="生成一张没有文字的封面背景",
        main_id="tenant_b",
        size="1536x864",
    )
    result = asyncio.run(model_endpoints.image_model_test("img_model_2", payload))

    assert result["code"] == 0
    assert result["data"]["success"] is True
    assert calls["output_spec"] == {"main_id": "tenant_b", "image_model_id": "img_model_2"}
    assert calls["size"] == "1536x864"
    assert calls["health"]["health_status"] == "healthy"
