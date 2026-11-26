import json

from app.services.image_model_configuration import (
    infer_image_runtime_kind,
    normalize_capabilities,
    normalize_image_settings,
    serialize_image_settings,
)


def test_image_edit_settings_round_trip_without_changing_generation_settings():
    raw = {"editRequestFormat": "json", "editRequestPath": "/images/generations", "editImageField": "image", "size": "1024*1024"}
    settings = normalize_image_settings(runtime_kind="openai_images", model_name="any-model", raw=raw)
    assert settings["edit_request_format"] == "json"
    assert settings["size"] == "1024*1024"
    assert serialize_image_settings(settings) == raw


def test_legacy_image_capability_is_normalized() -> None:
    assert normalize_capabilities(["chat", "image", "image_generation"]) == [
        "chat",
        "image_generation",
    ]


def test_qwen_provider_selects_dashscope_without_optional_defaults() -> None:
    provider = {
        "code": "qwen",
        "provider_type": "openai_compatible",
        "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    }
    runtime_kind = infer_image_runtime_kind(
        provider=provider,
        requested="",
        capabilities=["image_generation"],
        base_url="",
    )
    settings = normalize_image_settings(
        runtime_kind=runtime_kind,
        model_name="qwen-image-plus",
        raw={},
    )

    assert runtime_kind == "dashscope_image"
    assert settings == {}


def test_azure_image_config_does_not_add_optional_request_fields() -> None:
    provider = {"code": "azure-openai", "provider_type": "azure_openai"}
    runtime_kind = infer_image_runtime_kind(
        provider=provider,
        requested="",
        capabilities=["image_generation"],
        base_url="",
    )

    assert runtime_kind == "azure_openai_images"
    assert normalize_image_settings(
        runtime_kind=runtime_kind,
        model_name="gpt-image-1.5-production",
        raw={},
    ) == {"api_style": "v1", "include_api_version": False}


def test_custom_image_settings_preserve_fields_and_nested_json() -> None:
    settings = normalize_image_settings(
        runtime_kind="custom_images",
        model_name="agnes-image-2.5-flash",
        raw={
            "size": "2K",
            "ratio": "16:9",
            "quality": "",
            "n": None,
            "requestPath": "/images/generations",
            "responseUrlPath": "data.0.url",
            "extraParamsJson": '{"extra_body":{"response_format":"url"}}',
        },
    )

    assert settings == {
        "size": "2K",
        "ratio": "16:9",
        "request_path": "/images/generations",
        "response_url_path": "data.0.url",
        "response_base64_path": "data.0.b64_json",
        "extra_params": {"extra_body": {"response_format": "url"}},
    }
    serialized = serialize_image_settings(settings)
    assert serialized["size"] == "2K"
    assert serialized["ratio"] == "16:9"
    assert json.loads(serialized["extraParamsJson"]) == {"extra_body": {"response_format": "url"}}


def test_explicit_custom_runtime_is_not_overridden_by_provider() -> None:
    assert infer_image_runtime_kind(
        provider={"code": "qwen", "provider_type": "openai_compatible"},
        requested="custom_images",
        capabilities=["image_generation"],
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    ) == "custom_images"
