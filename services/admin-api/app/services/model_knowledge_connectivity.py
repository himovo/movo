from __future__ import annotations

import asyncio
from typing import Any

from app.repositories.model_repository import decrypt_secret
from app.services.image_model_configuration import normalize_capabilities
from app.services.setup_model_probe import (
    SetupKnowledgeProbeResult,
    SetupModelProbeError,
    probe_knowledge_model_details,
)


KNOWLEDGE_CAPABILITIES = ("embedding", "rerank")


class ModelKnowledgeConnectivityError(RuntimeError):
    pass


def resolve_knowledge_test_capability(instance: dict[str, Any], requested: str = "") -> str:
    capabilities = normalize_capabilities(instance.get("capabilities"))
    capability = str(requested or "").strip().lower()
    if capability:
        if capability not in KNOWLEDGE_CAPABILITIES:
            raise ModelKnowledgeConnectivityError(f"不支持的知识模型测试能力: {capability}")
        if capability not in capabilities:
            raise ModelKnowledgeConnectivityError(f"模型配置不支持能力: {capability}")
        return capability
    for candidate in KNOWLEDGE_CAPABILITIES:
        if candidate in capabilities:
            return candidate
    raise ModelKnowledgeConnectivityError("当前模型未配置 Embedding 或 Rerank 能力")


async def run_saved_knowledge_model_test(
    instance: dict[str, Any],
    provider: dict[str, Any],
    *,
    capability: str = "",
) -> SetupKnowledgeProbeResult:
    selected_capability = resolve_knowledge_test_capability(instance, capability)
    if str(instance.get("status") or "") != "active":
        raise ModelKnowledgeConnectivityError("模型配置已禁用")
    try:
        api_key = decrypt_secret(str(instance.get("api_key_encrypted") or ""))
    except Exception as exc:
        raise ModelKnowledgeConnectivityError("API Key 解密失败，请重新保存模型配置") from exc
    if not api_key:
        raise ModelKnowledgeConnectivityError("API Key 不能为空")

    model = {
        "capabilities": [selected_capability],
        "base_url": str(instance.get("base_url") or provider.get("default_base_url") or "").strip().rstrip("/"),
        "model_name": str(instance.get("model_name") or "").strip(),
        "api_key": api_key,
        "api_version": str(instance.get("api_version") or "").strip(),
    }
    if not model["base_url"]:
        raise ModelKnowledgeConnectivityError("Base URL 不能为空")
    if not model["model_name"]:
        raise ModelKnowledgeConnectivityError("模型 ID 不能为空")
    try:
        return await asyncio.to_thread(probe_knowledge_model_details, model, provider)
    except SetupModelProbeError as exc:
        raise ModelKnowledgeConnectivityError(str(exc)) from exc


__all__ = [
    "KNOWLEDGE_CAPABILITIES",
    "ModelKnowledgeConnectivityError",
    "resolve_knowledge_test_capability",
    "run_saved_knowledge_model_test",
]
