from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation, StepRecord
from app.enterprise_capabilities.browser.engine.agent_loop.model_input import build_browser_model_input
from app.llm.decision_turn import DecisionTurnSpec, DecisionTurnVisibility, invoke_structured_decision
from app.llm.factory import get_request_scoped_llm_client
from app.llm.types import Message, Role

from .structured_output import BrowserPlannerOutput, decision_from_output
from .decision_diagnostics import summarize_actions
from .guidance import build_guidance
from .planner_metrics import PlannerMeasurement
from .turn_payload import build_turn_payload
from .action_protocol import PlannerContractError, contract_repair_message


logger = logging.getLogger(__name__)


class Planner:
    def __init__(self, *, lang: str = "zh", enterprise_sites: Optional[Dict[str, str]] = None) -> None:
        self._lang = lang
        self._enterprise_sites = enterprise_sites or {}
        self._llm = get_request_scoped_llm_client(streaming=False, intent="chat")

    async def next_step(
        self,
        goal: str,
        history: List[StepRecord],
        observation: Observation,
        state_ledger: Optional[Dict[str, Any]] = None,
    ) -> Decision:
        payload = build_turn_payload(goal, history, observation, state_ledger)
        if self._enterprise_sites:
            payload["known_sites"] = dict(list(self._enterprise_sites.items())[:12])
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        model_input = build_browser_model_input(serialized, observation.screenshot)
        messages = [
            Message(role=Role.SYSTEM, content=build_guidance(observation.elements, lang=self._lang)),
            Message(role=Role.USER, content=model_input.content),
        ]
        try:
            with PlannerMeasurement(input_chars=len(str(messages[0].content or "")) + len(serialized)):
                try:
                    output = await self._invoke(messages, len(history) + 1)
                except PlannerContractError:
                    raise
                except Exception:
                    if not model_input.includes_screenshot:
                        raise
                    output = await self._invoke([
                        messages[0], Message(role=Role.USER, content=model_input.text_content),
                    ], len(history) + 1)
            decision = decision_from_output(output, observation)
            logger.info(
                "browser decision prepared",
                extra={
                    "event": "browser.decision",
                    "turn": len(history) + 1,
                    "output_kind": output.kind,
                    "proposed_tools": [action.tool for action in output.actions],
                    "proposed_actions": summarize_actions(output.actions, observation.elements),
                    "decision_tool": decision.tool,
                    "decision_reason": str(decision.rationale or "")[:500],
                    "element_count": len(observation.elements),
                    "revision": observation.revision,
                },
            )
            return decision
        except Exception as exc:
            logger.warning(
                "browser planner failed",
                extra={"event": "browser.planner_failed", "error": str(exc)[:500]},
            )
            return Decision(
                tool="browser_fail",
                args={
                    "reason": f"browser planner unavailable: {exc}",
                    "error_code": (
                        "planner_contract_invalid"
                        if isinstance(exc, PlannerContractError)
                        else "planner_internal_error"
                    ),
                },
                rationale="browser planner failed closed without an alternate planning path",
                rationale_source="system",
            )

    async def _invoke(self, messages: List[Message], turn: int) -> BrowserPlannerOutput:
        try:
            return await self._invoke_once(messages, turn)
        except ValidationError as first_error:
            logger.info(
                "browser planner contract repair requested",
                extra={
                    "event": "browser.contract_repair",
                    "turn": turn,
                    "status": "requested",
                    "error": str(first_error)[:500],
                },
            )
            repair_messages = [
                *messages,
                Message(role=Role.USER, content=contract_repair_message(first_error)),
            ]
            try:
                output = await self._invoke_once(repair_messages, turn)
            except ValidationError as second_error:
                raise PlannerContractError(
                    f"planner output violated the action contract after one repair: {second_error}"
                ) from second_error
            logger.info(
                "browser planner contract repair succeeded",
                extra={
                    "event": "browser.contract_repair",
                    "turn": turn,
                    "status": "succeeded",
                },
            )
            return output

    async def _invoke_once(self, messages: List[Message], turn: int) -> BrowserPlannerOutput:
        return await invoke_structured_decision(
            self._llm,
            BrowserPlannerOutput,
            messages,
            spec=DecisionTurnSpec(
                locale=self._lang,
                turn_id=f"browser.{turn}",
                visibility=DecisionTurnVisibility.INTERNAL,
            ),
        )
