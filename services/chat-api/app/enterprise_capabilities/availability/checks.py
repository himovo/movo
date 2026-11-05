"""Read dependency state without issuing billable model or search requests."""
from __future__ import annotations

import os
import httpx
from app.browser.registry import agent_registry
from app.core.config import get_settings
from app.llm.configured_models import get_default_model_config_by_capability, get_model_config_by_capability
from app.product.extensions import get_product_extension
from app.dsh_runtime.profile.search_availability import search_available
from app.services.presentation.availability import presentation_available


async def browser(tenant_id: str, user_id: str) -> bool:
    return agent_registry.get(user_id) is not None


async def profile_browser(tenant_id: str, user_id: str) -> bool:
    # A desktop socket is transient. Its absence must not rotate a durable
    # conversation profile; execution still checks the live connection.
    return True


async def images(tenant_id: str, user_id: str) -> bool:
    from app.services.image_generation import resolve_image_generation_model
    return bool(await resolve_image_generation_model(tenant_id, user_id))


async def vision_model(tenant_id: str, user_id: str):
    policy = get_product_extension().model_access_policy
    if policy is not None:
        model_id = await policy.resolve_model_id(
            main_id=tenant_id, user_id=user_id, model_id=None, capability="vision",
        )
        if not model_id:
            return None
        return await get_model_config_by_capability(str(model_id), tenant_id, capability="vision")
    return await get_default_model_config_by_capability(tenant_id, capability="vision")


async def vision(tenant_id: str, user_id: str) -> bool:
    return bool(get_settings().USE_MULTIMODAL and await vision_model(tenant_id, user_id))


async def search(tenant_id: str, user_id: str) -> bool:
    return await search_available(tenant_id)


async def profile_search(tenant_id: str, user_id: str) -> bool:
    from app.enterprise_capabilities.research.progressive.provider_router import ProviderRouter
    return bool(await ProviderRouter().available_providers(main_id=tenant_id, strict_config_lookup=True))


async def presentation(tenant_id: str, user_id: str) -> bool:
    return await presentation_available(tenant_id)


async def profile_presentation(tenant_id: str, user_id: str) -> bool:
    from app.services.presentation.availability import configured_presentation_available
    return await configured_presentation_available(tenant_id)


async def scripts(tenant_id: str, user_id: str) -> bool:
    endpoint = os.environ.get("MOVO_SANDBOX_MANAGER_URL", "").strip().rstrip("/")
    if not endpoint:
        # Local development retains the existing restricted subprocess backend.
        return True
    token = os.environ.get("MOVO_SANDBOX_MANAGER_TOKEN", "")
    if len(token) < 32:
        return False
    async with httpx.AsyncClient(timeout=0.7) as client:
        response = await client.get(endpoint + "/v1/readiness", headers={"Authorization": f"Bearer {token}"})
        return response.is_success and response.json().get("scripts") is True


async def profile_scripts(tenant_id: str, user_id: str) -> bool:
    endpoint = os.environ.get("MOVO_SANDBOX_MANAGER_URL", "").strip()
    return not endpoint or len(os.environ.get("MOVO_SANDBOX_MANAGER_TOKEN", "")) >= 32


async def skillhub(tenant_id: str, user_id: str) -> bool:
    return str(get_settings().SKILLHUB_API_BASE_URL or "").startswith(("https://", "http://"))


async def knowledge(tenant_id: str, user_id: str) -> bool:
    if not await profile_knowledge(tenant_id, user_id):
        return False
    from app.enterprise_capabilities.knowledge_source.config import get_knowledge_source
    source = await get_knowledge_source(tenant_id)
    if source.get("mode") == "external":
        return True
    endpoint = str(get_settings().DOCUMENT_PROCESSING_BASE_URL or "").strip().rstrip("/")
    async with httpx.AsyncClient(timeout=0.7) as client:
        response = await client.get(endpoint + "/health")
        return response.is_success


async def profile_knowledge(tenant_id: str, user_id: str) -> bool:
    from app.enterprise_capabilities.knowledge_source.config import get_knowledge_source
    from app.product.resource_access import resource_is_allowed
    from app.services.external_tools import external_tool_service
    source = await get_knowledge_source(tenant_id)
    if source.get("mode") == "external":
        tool_id = str(source.get("toolId") or "")
        tool = await external_tool_service.get(tool_id, tenant_id, scope="organization")
        if not tool or tool.get("status") != "active":
            return False
        if not await resource_is_allowed("tool", main_id=tenant_id, user_id=user_id, resource_id=tool_id):
            return False
        return tool.get("type") != "mcp" or str(source.get("mcpToolName") or "") in (tool.get("config") or {}).get("enabledToolNames", [])
    settings = get_settings()
    endpoint = str(settings.DOCUMENT_PROCESSING_BASE_URL or "").strip().rstrip("/")
    if not endpoint or not settings.DOCUMENT_PROCESSING_SERVICE_TOKEN:
        return False
    return True
