"""No-op context for browser tasks that don't need special handling.

Used when the category doesn't match any specialised context (plain
browse, open-URL-and-read, etc.). All hooks return the ABC defaults;
``active`` stays False because it has no specialised state machine.
"""
from __future__ import annotations

from .base import BrowserTaskContext


class NullContext(BrowserTaskContext):
    active: bool = False
