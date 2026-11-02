"""Resolve built-in presentation availability without network model probes."""
import logging

from app.llm.configured_models import ModelConfigError, get_model_config_by_capability
from .settings import get_presentation_generation_settings


async def _configured_presentation_available(tenant_id: str) -> bool:
    settings = await get_presentation_generation_settings(tenant_id)
    if not settings or not settings.get("enabled"):
        return False
    for key, capability in (("llm_model_id", "chat"), ("image_model_id", "image_generation"), ("vision_model_id", "vision")):
        model_id = settings.get(key)
        if not model_id:
            return False
        try:
            if not await get_model_config_by_capability(model_id, tenant_id, capability=capability):
                return False
        except ModelConfigError:
            return False
    return True


async def presentation_available(tenant_id: str) -> bool:
    try:
        return await _configured_presentation_available(tenant_id)
    except Exception:
        logging.getLogger(__name__).exception("presentation_availability_check_failed tenant_id=%s", tenant_id)
        return False
