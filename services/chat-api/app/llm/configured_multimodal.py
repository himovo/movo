from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.infrastructure.request_context import get_request_context
from app.llm.configured_models import (
    ModelConfigError,
    build_llm_client_from_config,
    get_configured_model_context,
)
from app.llm.types import Message, Role


@dataclass(frozen=True)
class ConfiguredMultimodalResult:
    model: str
    response: dict[str, Any]
    output_text: str
    usage: dict[str, int] = field(default_factory=dict)


def parse_json_object(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", raw, flags=re.IGNORECASE)
    if fenced:
        raw = fenced.group(1).strip()
    else:
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            raise ValueError("no JSON object found in model output")
        raw = match.group(0)
    return json.loads(raw)


class ConfiguredMultimodalClient:
    """Invoke the tenant-configured Vision model without provider-specific env vars."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._explicit_config = dict(config or {}) if config else None

    def _config(self) -> dict[str, Any]:
        if self._explicit_config:
            return dict(self._explicit_config)
        request_context = get_request_context()
        configured = request_context.get("vision_model_config")
        if not isinstance(configured, dict) or not configured:
            configured = get_configured_model_context()
        if not isinstance(configured, dict) or not configured:
            raise ModelConfigError("没有可用的视觉模型配置，请在管理端启用一个 Vision 模型")
        capabilities = {str(item).strip() for item in configured.get("capabilities") or []}
        if capabilities and "vision" not in capabilities:
            raise ModelConfigError("当前模型不支持 Vision 能力，请在管理端配置视觉模型")
        return dict(configured)

    async def call(
        self,
        *,
        prompt: str,
        image_b64: str | None = None,
        image_bytes: bytes | None = None,
        timeout_seconds: float | None = None,
        stage: str = "multimodal",
        intent: str = "generation",
        user_id: str = "",
        session_id: str = "",
        request_payload_extra: dict[str, Any] | None = None,
    ) -> ConfiguredMultimodalResult:
        del timeout_seconds, user_id, session_id
        if image_bytes and not image_b64:
            image_b64 = base64.b64encode(image_bytes).decode("ascii")

        content: list[dict[str, Any]] = []
        if image_b64:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{image_b64}"},
            })
        content.append({"type": "text", "text": str(prompt or "")})

        config = self._config()
        client = build_llm_client_from_config(
            config,
            streaming=False,
            intent=intent,
            stage=stage,
            output_spec={
                **dict(request_payload_extra or {}),
                "has_image": bool(image_b64),
            },
        )
        result = await client.ainvoke([Message(role=Role.USER, content=content)])
        return ConfiguredMultimodalResult(
            model=str(config.get("model_name") or ""),
            response=dict(result.raw_response or {}),
            output_text=str(result.message.content or ""),
            usage=dict(result.usage or {}),
        )

    async def call_json(self, **kwargs: Any) -> dict[str, Any]:
        result = await self.call(**kwargs)
        return parse_json_object(result.output_text)


__all__ = [
    "ConfiguredMultimodalClient",
    "ConfiguredMultimodalResult",
    "parse_json_object",
]
