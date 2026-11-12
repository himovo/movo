"""User approval policy for MOVO-owned script execution."""

from __future__ import annotations

def script_requires_approval() -> bool:
    """Script access is governed by capability policy, not per-call approval."""
    return False
