from __future__ import annotations

from typing import Any


IMAGE_CAPABILITY = "image_generation"
LEGACY_IMAGE_CAPABILITY = "image"
VALID_RUNTIME_KINDS = {
    "openai_images",
    "azure_openai_images",
    "dashscope_image",
}


def normalize_capabilities(raw: Any) -> list[str]:
    values = raw if isinstance(raw, (list, tuple, set)) else [raw]
    result: list[str] = []
    for value in values:
        token = str(value or "").strip()
        if token == LEGACY_IMAGE_CAPABILITY:
            token = IMAGE_CAPABILITY
        if token and token not in result:
            result.append(token)
    return result


def infer_image_runtime_kind(
    *,
    provider: dict[str, Any],
    requested: str,
    capabilities: list[str],
    base_url: str,
) -> str:
    if IMAGE_CAPABILITY not in normalize_capabilities(capabilities):
        return ""
    provider_type = str(provider.get("provider_type") or "").strip()
    provider_code = str(provider.get("code") or "").strip().lower()
    endpoint = str(base_url or provider.get("default_base_url") or "").lower()
    if provider_type == "azure_openai":
        return "azure_openai_images"
    if provider_code == "qwen" or "dashscope.aliyuncs.com" in endpoint:
        return "dashscope_image"
    explicit = str(requested or "").strip()
    if explicit in VALID_RUNTIME_KINDS:
        return explicit
    return "openai_images"


def normalize_image_settings(
    *,
    runtime_kind: str,
    model_name: str,
    raw: Any,
) -> dict[str, Any]:
    source = dict(raw or {}) if isinstance(raw, dict) else {}
    if not runtime_kind:
        return {}
    size = str(source.get("size") or "").strip()
    quality = str(source.get("quality") or "").strip()
    if not size:
        size = default_image_size(runtime_kind, model_name)
    if not quality:
        quality = "low" if runtime_kind == "azure_openai_images" or "gpt-image" in model_name.lower() else "standard"
    result: dict[str, Any] = {"size": size}
    if runtime_kind != "dashscope_image":
        result["quality"] = quality
    if runtime_kind == "azure_openai_images":
        api_style = str(
            source.get("api_style")
            or source.get("apiStyle")
            or source.get("generation_api_style")
            or "v1"
        ).strip()
        result["api_style"] = api_style if api_style in {"v1", "deployment"} else "v1"
        result["include_api_version"] = bool(
            source.get("include_api_version", source.get("includeApiVersion", False))
        )
    return result


def serialize_image_settings(settings: dict[str, Any]) -> dict[str, Any]:
    result = {
        "size": str(settings.get("size") or ""),
        "quality": str(settings.get("quality") or ""),
    }
    if "api_style" in settings:
        result["apiStyle"] = str(settings.get("api_style") or "v1")
    if "include_api_version" in settings:
        result["includeApiVersion"] = bool(settings.get("include_api_version"))
    return result


def default_image_size(runtime_kind: str, model_name: str) -> str:
    model = str(model_name or "").strip().lower()
    if runtime_kind == "dashscope_image":
        if model.startswith(("qwen-image-2", "qwen-image-3")):
            return "2048*1152"
        return "1664*928"
    if runtime_kind == "azure_openai_images":
        return "1536x864" if "gpt-image-2" in model else "1536x1024"
    if "gpt-image" in model:
        return "1536x1024"
    return "1024x1024"


__all__ = [
    "IMAGE_CAPABILITY",
    "VALID_RUNTIME_KINDS",
    "default_image_size",
    "infer_image_runtime_kind",
    "normalize_capabilities",
    "normalize_image_settings",
    "serialize_image_settings",
]
