"""Bounded recovery when a planner finishes before its context is ready."""
from __future__ import annotations

from dataclasses import dataclass

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision


@dataclass(frozen=True)
class DoneBlockResolution:
    retry: Decision | None = None
    terminal: bool = False
    attempts: int = 0


class DoneBlockRecovery:
    """Force fresh reconciliation, then stop a non-progressing done loop."""

    def __init__(self, *, max_attempts: int = 3) -> None:
        self.max_attempts = max(1, int(max_attempts))
        self.attempts = 0
        self.fingerprint = ""

    def blocked(self, *, fingerprint: str = "") -> DoneBlockResolution:
        current = str(fingerprint or "").strip()
        if current and self.fingerprint and current != self.fingerprint:
            self.attempts = 0
        if current:
            self.fingerprint = current
        self.attempts += 1
        if self.attempts >= self.max_attempts:
            return DoneBlockResolution(terminal=True, attempts=self.attempts)
        return DoneBlockResolution(
            retry=Decision(
                tool="browser_observe",
                args={},
                rationale="system reconciliation after context rejected browser_done",
            ),
            attempts=self.attempts,
        )

    def record_action(self, decision: Decision) -> None:
        # A forced observation is recovery, not proof of mission progress.
        # Any substantive action, including a context-owned deterministic one,
        # starts a genuinely new completion attempt chain.
        if decision.tool not in {"browser_done", "browser_observe"}:
            self.attempts = 0
            self.fingerprint = ""


__all__ = ["DoneBlockRecovery", "DoneBlockResolution"]
