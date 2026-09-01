from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, Tuple

from app.enterprise_capabilities.runtime.execution_contracts import CapabilityTask
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityInputs


class BaseExecutor(ABC):
    @abstractmethod
    def can_handle(self, node: CapabilityTask) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def execute(
        self,
        *,
        runtime: Any,
        task_id: str,
        run_id: str,
        node: CapabilityTask,
        inputs: CapabilityInputs,
        skills: Dict[str, Any],
    ) -> AsyncIterator[Tuple[Dict[str, Any], Dict[str, Any]]]:
        raise NotImplementedError

