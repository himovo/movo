"""Read native context measurements through the existing conversation binding."""

from typing import Any

from app.dsh_runtime.errors import DshRuntimeError


class ContextUsageReader:
    def __init__(self, *, bindings, coordinator, gateway) -> None:
        self._bindings = bindings
        self._coordinator = coordinator
        self._gateway = gateway

    async def read(self, conversation_id: str, *, tenant_id: str, user_id: str) -> dict[str, Any]:
        binding = await self._bindings.current(conversation_id, tenant_id=tenant_id, user_id=user_id)
        if not binding:
            return {"available": False, "reason": "no_runtime_session"}
        try:
            await self._coordinator.restore(binding)
            usage = await self._gateway.context_usage(str(binding["kernel_session_id"]))
        except DshRuntimeError:
            return {"available": False, "reason": "runtime_unavailable"}
        current = await self._bindings.current(conversation_id, tenant_id=tenant_id, user_id=user_id)
        if not current or current["binding_id"] != binding["binding_id"]:
            return {"available": False, "reason": "binding_changed"}
        return {**usage, "modelInstanceId": str(binding.get("model_instance_id") or "")}
