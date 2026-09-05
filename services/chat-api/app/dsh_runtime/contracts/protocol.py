"""Kernel-neutral asynchronous interface consumed by ASKAI application code."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

from .events import KernelEventEnvelope
from .kernel import (
    CancelSessionRequest,
    CreateRuntimeRequest,
    CreateSessionRequest,
    RuntimeHandle,
    SendRequest,
    SessionHandle,
)


class AgentKernelContract(Protocol):
    async def create_runtime(self, request: CreateRuntimeRequest) -> RuntimeHandle: ...

    async def dispose_runtime(self, runtime_id: str) -> None: ...

    async def create_session(self, request: CreateSessionRequest) -> SessionHandle: ...

    async def resume_session(self, session_id: str) -> SessionHandle: ...

    async def send(self, request: SendRequest) -> str: ...

    async def cancel(self, request: CancelSessionRequest) -> dict[str, Any]: ...

    async def dispose_session(self, session_id: str) -> None: ...

    def subscribe(self, session_id: str, after_cursor: int = 0) -> AsyncIterator[KernelEventEnvelope]: ...
