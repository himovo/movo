from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


def resolve_image_runtime_kind(config: dict[str, Any]) -> str:
    provider_type = str(config.get("provider_type") or "openai_compatible").strip()
    provider_code = str(config.get("provider_code") or "").strip().lower()
    provider_name = str(config.get("provider_name") or "").strip().lower()
    endpoint = str(config.get("base_url") or "").strip().lower()
    if provider_type == "azure_openai":
        return "azure_openai_images"
    if provider_code == "qwen" or "通义千问" in provider_name or "dashscope.aliyuncs.com" in endpoint:
        return "dashscope_image"
    explicit = str(config.get("runtime_kind") or "").strip()
    if explicit in {"openai_images", "azure_openai_images", "dashscope_image"}:
        return explicit
    return "openai_images"


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


def default_image_quality(runtime_kind: str, model_name: str) -> str:
    model = str(model_name or "").strip().lower()
    if runtime_kind == "azure_openai_images" or "gpt-image" in model:
        return "low"
    return "standard"


def dashscope_native_endpoint(base_url: str) -> str:
    raw = str(base_url or "https://dashscope.aliyuncs.com").strip().rstrip("/")
    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        root = f"{parsed.scheme}://{parsed.netloc}"
    else:
        root = "https://dashscope.aliyuncs.com"
    return f"{root}/api/v1/services/aigc/multimodal-generation/generation"


__all__ = [
    "dashscope_native_endpoint",
    "default_image_quality",
    "default_image_size",
    "resolve_image_runtime_kind",
]
