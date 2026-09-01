from __future__ import annotations

from typing import Any

from app.llm.configured_models import get_model_config
from app.infrastructure.request_context import reset_request_context, set_request_context

from .contracts import CapabilityExecutionContext
from .registry import CapabilityHandlerRegistry


class InternalCapabilityService:
    def __init__(self, registry: CapabilityHandlerRegistry) -> None:
        self._registry = registry

    async def execute(
        self,
        capability_ref: str,
        arguments: dict[str, Any],
        context: CapabilityExecutionContext,
    ) -> dict[str, Any]:
        handler = self._registry.require(capability_ref)
        configured_model = None
        if context.model_instance_id:
            configured_model = await get_model_config(context.model_instance_id, context.tenant_id)
            if configured_model is None:
                raise LookupError("the capability's immutable model instance is unavailable")
        previous = set_request_context({
            "main_id": context.tenant_id,
            "user_id": context.user_id,
            "configured_model": configured_model or {},
        })
        try:
            result = await handler(dict(arguments), context)
        finally:
            reset_request_context(previous)
        if not isinstance(result, dict):
            raise TypeError(f"capability {capability_ref} returned a non-object result")
        return result
