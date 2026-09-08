from app.llm.image_model_runtime import (
    dashscope_native_endpoint,
    default_image_quality,
    default_image_size,
    resolve_image_runtime_kind,
)


def test_existing_qwen_config_is_inferred_without_runtime_kind() -> None:
    assert resolve_image_runtime_kind({
        "provider_code": "qwen",
        "provider_type": "openai_compatible",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    }) == "dashscope_image"


def test_existing_azure_config_is_inferred_without_runtime_kind() -> None:
    assert resolve_image_runtime_kind({"provider_type": "azure_openai"}) == "azure_openai_images"


def test_landscape_defaults_are_provider_and_model_aware() -> None:
    assert default_image_size("dashscope_image", "qwen-image-plus") == "1664*928"
    assert default_image_size("dashscope_image", "qwen-image-3.0") == "2048*1152"
    assert default_image_size("azure_openai_images", "gpt-image-1.5") == "1536x1024"
    assert default_image_size("azure_openai_images", "gpt-image-2") == "1536x864"
    assert default_image_quality("openai_images", "gpt-image-1") == "low"


def test_dashscope_native_endpoint_preserves_configured_region_host() -> None:
    assert dashscope_native_endpoint(
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    ) == "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
