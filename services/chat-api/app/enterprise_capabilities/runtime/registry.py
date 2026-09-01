from __future__ import annotations

from typing import Any, Awaitable, Callable

from .contracts import CapabilityExecutionContext


CapabilityHandler = Callable[[dict[str, Any], CapabilityExecutionContext], Awaitable[dict[str, Any]]]


class CapabilityHandlerRegistry:
    """One execution registry for all MOVO-owned DSH capability adapters."""

    def __init__(self) -> None:
        self._handlers: dict[str, CapabilityHandler] = {}

    def register(self, capability_ref: str, handler: CapabilityHandler) -> None:
        if capability_ref in self._handlers:
            raise ValueError(f"duplicate capability handler: {capability_ref}")
        self._handlers[capability_ref] = handler

    def require(self, capability_ref: str) -> CapabilityHandler:
        try:
            return self._handlers[capability_ref]
        except KeyError as exc:
            raise LookupError(f"capability handler is unavailable: {capability_ref}") from exc

    def refs(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))
