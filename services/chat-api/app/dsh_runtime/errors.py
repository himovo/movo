"""Explicit failure types for the DSH kernel boundary."""


class DshRuntimeError(RuntimeError):
    """Base error for a failed DSH host or request."""


class DshTransportError(DshRuntimeError):
    """The Runtime Host could not be reached or returned an invalid response."""


class DshProtocolError(DshRuntimeError):
    """The Runtime Host violated the pinned AgentKernel protocol."""


class DshNotFoundError(DshRuntimeError):
    """The requested ASKAI-owned runtime/session binding does not exist."""
