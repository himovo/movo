from app.services.image_model_configuration import (
    infer_image_runtime_kind,
    normalize_capabilities,
    normalize_image_settings,
)


def test_legacy_image_capability_is_normalized() -> None:
    assert normalize_capabilities(["chat", "image", "image_generation"]) == [
        "chat",
        "image_generation",
    ]


def test_qwen_provider_selects_dashscope_and_landscape_size() -> None:
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
    assert settings["size"] == "1664*928"


def test_azure_image_defaults_follow_deployment_generation() -> None:
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
    )["size"] == "1536x1024"
    assert normalize_image_settings(
        runtime_kind=runtime_kind,
        model_name="gpt-image-2-production",
        raw={},
    )["size"] == "1536x864"
