from __future__ import annotations

import re
from typing import Any


NATIVE_STRUCTURED_OUTPUT_MODES = {"native", "openai_native", "azure_native", "json_schema"}
PROMPT_STRUCTURED_OUTPUT_MODES = {"prompt_json", "json_prompt", "text_json", "fallback", "disabled", "none"}


def model_supports_capability(config: dict[str, Any] | None, capability: str) -> bool:
    """Return explicit model capabilities from the admin/runtime config.

    Input modalities are fail-closed: an absent capability never implies that
    the provider accepts that payload shape.
    """
    if not isinstance(config, dict):
        return False
    expected = str(capability or "").strip().lower()
    if not expected:
        return False
    raw = config.get("capabilities")
    if isinstance(raw, str):
        capabilities = [raw]
    elif isinstance(raw, (list, tuple, set)):
        capabilities = list(raw)
    else:
        capabilities = []
    return expected in {str(item).strip().lower() for item in capabilities if str(item).strip()}


def normalize_structured_output_mode(value: Any) -> str:
    token = str(value or "").strip().lower()
    if token in NATIVE_STRUCTURED_OUTPUT_MODES:
        return "native"
    if token in PROMPT_STRUCTURED_OUTPUT_MODES:
        return "prompt_json"
    return ""


def infer_structured_output_mode(
    *,
    provider_type: str = "",
    provider_name: str = "",
    model_name: str = "",
    settings: dict[str, Any] | None = None,
    api_version: str = "",
    default_openai_native: bool = True,
) -> str:
    config_settings = settings if isinstance(settings, dict) else {}
    explicit = normalize_structured_output_mode(
        config_settings.get("structured_output_mode")
        or config_settings.get("structuredOutputMode")
        or config_settings.get("response_format_mode")
        or config_settings.get("responseFormatMode")
    )
    if explicit:
        return explicit

    provider = str(provider_type or "").strip().lower()
    provider_label = f"{provider_name} {model_name}".lower()
    if provider == "azure_openai":
        match = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(api_version or ""))
        if not match:
            return "prompt_json"
        version = tuple(int(part) for part in match.groups())
        return "native" if version >= (2024, 8, 1) else "prompt_json"
    if provider in {"openai", "openai_native"}:
        return "native"
    if "deepseek" in provider_label or "qwen" in provider_label or "dashscope" in provider_label:
        return "prompt_json"
    if provider == "openai_compatible":
        return "prompt_json"
    return "native" if default_openai_native else "prompt_json"
