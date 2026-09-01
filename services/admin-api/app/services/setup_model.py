from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass
from typing import Any

from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError

from app.repositories.model_repository import (
    create_instance,
    delete_instance,
    find_provider_by_id,
    list_providers,
)
from app.services.model_connectivity import run_saved_model_test
from app.services.setup_model_probe import SetupModelProbeError, probe_knowledge_model_details


class SetupModelError(ValueError):
    pass


@dataclass(frozen=True)
class SetupModelInspection:
    message: str
    dimension: int | None = None


def format_provider(provider: dict[str, Any]) -> dict[str, object]:
    return {
        "id": str(provider.get("_id") or ""),
        "name": str(provider.get("name") or ""),
        "code": str(provider.get("code") or ""),
        "providerType": str(provider.get("provider_type") or "openai_compatible"),
        "defaultBaseUrl": str(provider.get("default_base_url") or ""),
    }


async def get_active_setup_providers() -> list[dict[str, object]]:
    return [format_provider(item) for item in await list_providers() if item.get("status") == "active"]


async def test_setup_model(payload: dict[str, Any]) -> str:
    return (await inspect_setup_model(payload)).message


async def inspect_setup_model(payload: dict[str, Any]) -> SetupModelInspection:
    provider = await _require_provider(str(payload.get("providerId") or ""))
    normalized = _normalize_payload(payload, provider)
    capability = str((normalized.get("capabilities") or ["chat"])[0])
    if capability in {"embedding", "rerank"}:
        try:
            result = await asyncio.to_thread(probe_knowledge_model_details, normalized, provider)
            return SetupModelInspection(message=result.message, dimension=result.dimension)
        except SetupModelProbeError as exc:
            raise SetupModelError(str(exc)) from exc
    temporary_main_id = f"setup-test-{secrets.token_hex(12)}"
    instance_id = ""
    try:
        instance_id = await create_instance({**normalized, "main_id": temporary_main_id})
        success, message = await run_saved_model_test(instance_id, temporary_main_id)
        if not success:
            raise SetupModelError(message)
        return SetupModelInspection(message=message)
    finally:
        if instance_id:
            await delete_instance(instance_id, temporary_main_id)


# The public service function name is retained for API compatibility; prevent
# pytest from collecting it when imported into a test module.
test_setup_model.__test__ = False


async def create_setup_model(payload: dict[str, Any], main_id: str) -> str:
    provider = await _require_provider(str(payload.get("providerId") or ""))
    normalized = _normalize_payload(payload, provider)
    try:
        return await create_instance({**normalized, "main_id": main_id})
    except DuplicateKeyError as exc:
        raise SetupModelError("The model configuration already exists.") from exc


async def _require_provider(provider_id: str) -> dict[str, Any]:
    try:
        provider = await find_provider_by_id(provider_id)
    except InvalidId as exc:
        raise SetupModelError("Invalid model provider.") from exc
    if provider is None or provider.get("status") != "active":
        raise SetupModelError("The selected model provider is unavailable.")
    return provider


def _normalize_payload(payload: dict[str, Any], provider: dict[str, Any]) -> dict[str, Any]:
    provider_type = str(provider.get("provider_type") or "openai_compatible")
    model_name = str(payload.get("modelName") or "").strip()
    api_key = str(payload.get("apiKey") or "").strip()
    base_url = str(payload.get("baseUrl") or provider.get("default_base_url") or "").strip().rstrip("/")
    api_version = str(payload.get("apiVersion") or "").strip()
    capability = str(payload.get("capability") or "chat").strip().lower()
    if capability not in {"chat", "embedding", "rerank", "vision", "image"}:
        raise SetupModelError("Unsupported model capability.")
    if not model_name:
        raise SetupModelError("Model ID is required.")
    if not api_key:
        raise SetupModelError("API Key is required.")
    if not base_url:
        raise SetupModelError("Base URL is required.")
    if not base_url.startswith(("https://", "http://")):
        raise SetupModelError("Base URL must start with http:// or https://.")
    if provider_type == "azure_openai" and not api_version:
        raise SetupModelError("API Version is required for Azure OpenAI.")
    return {
        "provider_id": str(provider.get("_id")),
        "org_id": "",
        "display_name": str(payload.get("displayName") or model_name).strip() or model_name,
        "model_name": model_name,
        "base_url": base_url,
        "api_version": api_version,
        "api_key": api_key,
        "api_secret": "",
        "capabilities": [capability],
        "max_context_tokens": 0,
        "status": "active",
        # Runtime selects from the tenant's configured models by priority. There is
        # no platform/global default model in a self-hosted deployment.
        "is_default": False,
        "priority": 10,
    }
