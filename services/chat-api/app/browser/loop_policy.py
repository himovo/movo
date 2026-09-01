"""Shared browser-loop limits used by enforcement and planner guidance."""

from __future__ import annotations


BROWSER_MAX_STEPS = 500
BROWSER_MAX_READS_PER_STATE = 3


__all__ = ["BROWSER_MAX_READS_PER_STATE", "BROWSER_MAX_STEPS"]
