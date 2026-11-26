from __future__ import annotations

import json
from typing import Any


IMAGE_CAPABILITY = "image_generation"
LEGACY_IMAGE_CAPABILITY = "image"
VALID_RUNTIME_KINDS = {
    "openai_images",
    "azure_openai_images",
    "dashscope_image",
    "custom_images",
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
    explicit = str(requested or "").strip()
    if explicit in VALID_RUNTIME_KINDS:
        return explicit
    provider_type = str(provider.get("provider_type") or "").strip()
    provider_code = str(provider.get("code") or "").strip().lower()
    endpoint = str(base_url or provider.get("default_base_url") or "").lower()
    if provider_type == "azure_openai":
        return "azure_openai_images"
    if provider_code == "qwen" or "dashscope.aliyuncs.com" in endpoint:
        return "dashscope_image"
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
    del model_name
    result: dict[str, Any] = {}
    edit_format = str(source.get("edit_request_format", source.get("editRequestFormat", "")) or "")
    if edit_format in {"json", "multipart"}:
        result["edit_request_format"] = edit_format
    for key, camel in (("edit_request_path", "editRequestPath"), ("edit_image_field", "editImageField")):
        value = str(source.get(key, source.get(camel, "")) or "").strip()
        if value:
            result[key] = value
    for key, camel_key in (
        ("size", "size"),
        ("quality", "quality"),
        ("output_format", "outputFormat"),
        ("response_format", "responseFormat"),
        ("ratio", "ratio"),
    ):
        value = str(source.get(key, source.get(camel_key, "")) or "").strip()
        if value:
            result[key] = value
    raw_n = source.get("n")
    if raw_n not in (None, ""):
        count = int(raw_n)
        if not 1 <= count <= 10:
            raise ValueError("图片生成数量 n 必须在 1 到 10 之间")
        result["n"] = count
    if runtime_kind == "custom_images":
        request_path = str(source.get("request_path", source.get("requestPath", "")) or "").strip()
        result["request_path"] = request_path or "/images/generations"
        result["response_url_path"] = str(
            source.get("response_url_path", source.get("responseUrlPath", "")) or "data.0.url"
        ).strip()
        result["response_base64_path"] = str(
            source.get("response_base64_path", source.get("responseBase64Path", "")) or "data.0.b64_json"
        ).strip()
        raw_extra = source.get("extra_params", source.get("extraParams", source.get("extraParamsJson", {})))
        if isinstance(raw_extra, str):
            raw_extra = json.loads(raw_extra or "{}")
        if not isinstance(raw_extra, dict):
            raise ValueError("额外请求参数必须是 JSON 对象")
        if len(json.dumps(raw_extra, ensure_ascii=False)) > 20000:
            raise ValueError("额外请求参数不能超过 20000 个字符")
        result["extra_params"] = raw_extra
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
    result: dict[str, Any] = {}
    for key, camel_key in (
        ("size", "size"),
        ("quality", "quality"),
        ("output_format", "outputFormat"),
        ("response_format", "responseFormat"),
        ("ratio", "ratio"),
        ("n", "n"),
        ("request_path", "requestPath"),
        ("edit_request_format", "editRequestFormat"),
        ("edit_request_path", "editRequestPath"),
        ("edit_image_field", "editImageField"),
        ("response_url_path", "responseUrlPath"),
        ("response_base64_path", "responseBase64Path"),
    ):
        if key in settings:
            result[camel_key] = settings[key]
    if "extra_params" in settings:
        result["extraParamsJson"] = json.dumps(settings["extra_params"], ensure_ascii=False, indent=2)
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
