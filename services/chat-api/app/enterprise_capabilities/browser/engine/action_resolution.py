"""Resolve a text-located browser action without reopening the full planner.

High-confidence local rule matches are clicked directly. Ambiguous or unknown
matches use a narrow LLM picker whose dynamic schema only permits refs present
in the supplied candidate set. Every selected ref is validated again before a
Decision is returned to the executor.
"""

from __future__ import annotations

from enum import Enum
import json
import logging
from typing import Any, Dict, List, Literal, Mapping, Optional, Sequence

from pydantic import BaseModel, Field, create_model

from app.llm.factory import get_request_scoped_llm_client
from app.llm.types import Message, Role
from app.llm.decision_turn import DecisionOutput, DecisionTurnSpec, invoke_structured_decision
from app.enterprise_capabilities.browser.engine.local_candidate_policy import (
    is_actionable_candidate,
    unique_exact_action_ref,
)
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


logger = logging.getLogger(__name__)


class ResolvedAction(BaseModel):
    decision: Optional[Decision] = None
    source: Literal["local_rule", "model_candidate", "none"] = "none"
    allowed_refs: List[str] = Field(default_factory=list)


async def resolve_wait_for_action(
    *,
    goal: str,
    query: str,
    result: Any,
    observation: Observation,
    domain: str,
    lang: str,
    llm: Any = None,
) -> ResolvedAction:
    if not isinstance(result, Mapping):
        return ResolvedAction()

    if (
        result.get("matched") is True
        and result.get("resolution") == "action_rule"
        and not result.get("model_required")
    ):
        ref = str(result.get("clickable_ref") or "").strip()
        if _current_candidate(ref, observation, [ref]):
            return ResolvedAction(
                decision=Decision(
                    tool="browser_click",
                    args={"ref": ref, "domain": domain},
                    rationale=f"local action rule resolved {query!r} to {ref}",
                ),
                source="local_rule",
                allowed_refs=[ref],
            )
        return ResolvedAction()

    if not result.get("model_required"):
        return ResolvedAction()
    candidates = _candidate_list(result.get("candidates"), observation)
    if not candidates:
        return ResolvedAction()

    refs = [item["ref"] for item in candidates]
    local_ref = unique_exact_action_ref(
        query=query,
        candidates=candidates,
        observation=observation,
    )
    if local_ref:
        return ResolvedAction(
            decision=Decision(
                tool="browser_click",
                args={"ref": local_ref, "domain": domain},
                rationale=f"unique exact action candidate resolved {query!r} to {local_ref}",
            ),
            source="local_rule",
            allowed_refs=refs,
        )

    client = llm or get_request_scoped_llm_client(
        streaming=False,
        intent="chat",
        stage="browser_candidate_selection",
    )
    schema = _selection_schema(refs)
    messages = _selection_messages(goal=goal, query=query, candidates=candidates, lang=lang)
    try:
        selected = await invoke_structured_decision(
            client, schema, messages,
            spec=DecisionTurnSpec(locale=lang, turn_id="browser.candidate_selection"),
        )
        payload = selected.model_dump(mode="json")
    except Exception as exc:
        logger.warning(
            "browser candidate selection failed",
            extra={"event": "browser.candidate_selection_failed", "error": str(exc)},
        )
        return ResolvedAction(source="none", allowed_refs=refs)

    if payload.get("action") != "click":
        return ResolvedAction(source="none", allowed_refs=refs)
    ref = str(payload.get("selected_ref") or "").strip()
    if not _current_candidate(ref, observation, refs):
        logger.warning(
            "browser candidate selection rejected",
            extra={"event": "browser.candidate_selection_rejected", "ref": ref, "allowed_refs": refs},
        )
        return ResolvedAction(source="none", allowed_refs=refs)
    return ResolvedAction(
        decision=Decision(
            tool="browser_click",
            args={"ref": ref, "domain": domain},
            rationale=f"constrained candidate selection resolved {query!r} to {ref}",
        ),
        source="model_candidate",
        allowed_refs=refs,
    )


def _selection_schema(refs: Sequence[str]) -> type[BaseModel]:
    ref_enum = Enum(
        "BrowserCandidateRef",
        {f"candidate_{index + 1}": ref for index, ref in enumerate(refs)},
        type=str,
    )
    return create_model(
        "BrowserCandidateSelection",
        __base__=DecisionOutput,
        action=(Literal["click", "none"], ...),
        selected_ref=(Optional[ref_enum], None),
        rationale=(str, ""),
    )


def _selection_messages(*, goal: str, query: str, candidates: List[Dict[str, str]], lang: str) -> List[Message]:
    if lang == "zh":
        system = (
            "你只负责判断一个浏览器文字定位结果。只能从用户消息提供的候选 ref 中选择，"
            "不得生成其他 ref。如果查询文字表示需要点击的动作，选择最符合目标的候选并返回 click；"
            "如果查询只是等待文字出现、候选语义不符或无法确定，返回 none。"
        )
    else:
        system = (
            "You only resolve one browser text-location result. Select only a ref listed in the user message; "
            "never invent another ref. Return click only when the query represents an action and one candidate "
            "fits the goal. Otherwise return none."
        )
    payload = {"goal": goal, "query": query, "candidates": candidates}
    return [
        Message(role=Role.SYSTEM, content=system),
        Message(role=Role.USER, content=json.dumps(payload, ensure_ascii=False)),
    ]


def _candidate_list(raw: Any, observation: Observation) -> List[Dict[str, str]]:
    if not isinstance(raw, list):
        return []
    current = {
        str(item.get("ref") or "").strip(): item
        for item in list(observation.elements or [])
        if isinstance(item, Mapping) and str(item.get("ref") or "").strip()
    }
    candidates: List[Dict[str, str]] = []
    seen = set()
    for item in raw[:8]:
        if not isinstance(item, Mapping):
            continue
        ref = str(item.get("ref") or "").strip()
        element = current.get(ref)
        if not ref or ref in seen or element is None:
            continue
        if not is_actionable_candidate(element, item):
            continue
        seen.add(ref)
        candidates.append({
            "ref": ref,
            "role": str(item.get("role") or ""),
            "name": str(item.get("name") or item.get("text") or "")[:160],
        })
    return candidates


def _current_candidate(ref: str, observation: Observation, allowed_refs: Sequence[str]) -> bool:
    if not ref or ref not in set(allowed_refs):
        return False
    return any(
        isinstance(item, Mapping)
        and str(item.get("ref") or "").strip() == ref
        and is_actionable_candidate(item)
        for item in list(observation.elements or [])
    )
