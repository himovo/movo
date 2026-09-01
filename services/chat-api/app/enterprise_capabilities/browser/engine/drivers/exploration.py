"""LLM-driven free exploration.

A thin adapter over the existing browser-task planner. Instantiating
the driver is functionally identical to instantiating ``Planner``
directly — preserved on purpose so the Driver abstraction is a pure
refactor with zero behaviour change for any task that lacks a recorded
skill.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.enterprise_capabilities.browser.engine.agent_loop.planner import Planner
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import (
    Decision,
    Observation,
    StepRecord,
)

from .base import BrowserDriver


class ExplorationDriver(BrowserDriver):
    """Wraps :class:`Planner` 1:1.

    Constructed with the same args as the legacy planner. ``next_step``
    delegates straight through. ``on_step_completed`` is a no-op
    because the planner is stateless across turns — every decision is
    re-derived from the full history each call.
    """

    def __init__(
        self,
        *,
        lang: str = "zh",
        enterprise_sites: Optional[Dict[str, str]] = None,
    ) -> None:
        self._planner = Planner(lang=lang, enterprise_sites=enterprise_sites)

    @property
    def kind(self) -> str:
        return "exploration"

    async def next_step(
        self,
        goal: str,
        history: List[StepRecord],
        observation: Observation,
        state_ledger: Optional[Dict[str, Any]] = None,
    ) -> Decision:
        return await self._planner.next_step(
            goal,
            history,
            observation,
            state_ledger=state_ledger,
        )
