from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation, StepRecord
from app.enterprise_capabilities.browser.engine.drivers.base import BrowserDriver

from app.enterprise_capabilities.browser.engine.agent_loop.planner import Planner


class ExplorationDriver(BrowserDriver):
    def __init__(self, *, lang: str = "zh", enterprise_sites: Optional[Dict[str, str]] = None) -> None:
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
        return await self._planner.next_step(goal, history, observation, state_ledger)
