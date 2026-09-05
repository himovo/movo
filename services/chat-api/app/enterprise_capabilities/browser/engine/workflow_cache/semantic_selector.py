from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Literal, Sequence

from pydantic import BaseModel, Field

from app.llm.base import BaseLLMClient
from app.llm.factory import get_request_scoped_llm_client
from app.llm.types import Message, Role
from app.enterprise_capabilities.browser.engine.form_input.input_context import BrowserInputContext

from .contracts import CachedBrowserWorkflow, CachedWorkflowStep
from .control_semantics import infer_control_semantic
from .semantic_inputs import SemanticInputValue


logger = logging.getLogger(__name__)


class BrowserWorkflowRequirement(BaseModel):
    kind: Literal[
        "replay_action",
        "runtime_precondition",
        "completion_verification",
    ]
    description: str = Field(min_length=1, max_length=500)
    safe_cached_prefix_steps: int = Field(default=-1, ge=-1)
    category: Literal[
        "authentication", "challenge", "approval", "human_assistance", "none",
    ] = "none"


class WorkflowSelectionResponse(BaseModel):
    selected_workflow_id: str = ""
    matching_workflow_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = ""
    parameter_values: list[SemanticInputValue] = Field(default_factory=list)
    replay_step_count: int = Field(default=-1, ge=-1)
    missing_input_roles: list[str] = Field(default_factory=list)
    browser_requirements: list[BrowserWorkflowRequirement] = Field(default_factory=list)


@dataclass(frozen=True)
class SemanticWorkflowSelection:
    workflow: CachedBrowserWorkflow
    confidence: float
    reason: str = ""
    matching_workflows: tuple[CachedBrowserWorkflow, ...] = ()
    parameter_values: tuple[SemanticInputValue, ...] = ()
    replay_step_count: int = -1
    missing_input_roles: tuple[str, ...] = ()
    browser_requirements: tuple[BrowserWorkflowRequirement, ...] = ()


class WorkflowSemanticSelector:
    """Use one small semantic decision to choose among same-site workflows."""

    def __init__(
        self,
        *,
        llm: BaseLLMClient | None = None,
        min_confidence: float = 0.72,
    ) -> None:
        self._llm = llm or get_request_scoped_llm_client(
            streaming=False,
            stage="browser_cache_matching",
            intent="browser_automation",
        )
        # Kept as a constructor argument for compatibility with callers.  LLM
        # confidence is intentionally telemetry-only: it is not calibrated
        # enough to veto an explicit same-operation classification.
        self._legacy_min_confidence = min(max(float(min_confidence), 0.0), 1.0)

    async def select(
        self,
        *,
        site_id: str,
        context: BrowserInputContext,
        current_operation_id: str,
        current_capability_id: str,
        candidates: Sequence[CachedBrowserWorkflow],
        browser_goal: str = "",
    ) -> SemanticWorkflowSelection | None:
        if not candidates:
            return None
        by_id = {item.workflow_id: item for item in candidates}
        resolved_site = str(site_id or "").strip()
        candidate_scope = "same_site" if resolved_site else "same_user_cross_site_fallback"
        payload = {
            "current_task": {
                # The node goal is the browser operation boundary. The full
                # request may also contain completed upstream work such as
                # downloading, querying, or generating the values used here.
                "browser_goal": str(browser_goal or context.original_request or "").strip(),
                "user_request_for_parameter_extraction": str(
                    context.original_request or ""
                ).strip(),
                "resolved_site": resolved_site,
                "inferred_operation": str(current_operation_id or "").strip(),
                "inferred_capability": str(current_capability_id or "").strip(),
                "available_input_roles": _input_roles(context),
            },
            "candidate_scope": candidate_scope,
            "cached_workflows": [_workflow_summary(item) for item in candidates],
            "decision_rules": [
                (
                    "Return every workflow_id that performs the same business operation on the resolved site."
                    if resolved_site else
                    "First infer the destination product/site from the request and each candidate site_id; return only workflows on that one site that perform the same business operation."
                ),
                "Set selected_workflow_id to the semantically clearest member of that group; route health is ranked locally later.",
                "Treat capability and operation labels as fallible hints, not exact-match requirements.",
                "Use the requested outcome, input roles, terminal action, and step outline as primary evidence.",
                "Keep materially different outcomes separate, such as save draft, publish, delete, search, and edit.",
                "Return empty matching_workflow_ids and selected_workflow_id when no candidate performs the same operation.",
                "A current task may require additional inputs beyond a cached workflow; that is partial reuse, not a different business operation.",
                "For the selected workflow, extract parameter_values for its input_roles when their values are explicitly present in user_request_for_parameter_extraction; never invent or paraphrase values.",
                "Use browser_goal, not user_request_for_parameter_extraction, to decide workflow equivalence and replay_step_count.",
                "Ignore upstream preparation outside browser_goal (for example downloading files, querying data, or generating content) when calculating the cached browser prefix.",
                "Classify every apparent uncovered browser requirement in browser_requirements: replay_action means a concrete executable navigation/interaction absent from the cached outline; runtime_precondition means authentication, CAPTCHA, approval, or human assistance that the executor can pause for; completion_verification means evidence checked after the cached terminal action.",
                "Only replay_action can shorten replay. runtime_precondition and completion_verification never make an otherwise complete cached route partial.",
                "For each replay_action, set safe_cached_prefix_steps to the number of leading cached steps executable before that missing action. Use -1 for the other two kinds.",
                "For every runtime_precondition, set category to authentication, challenge, approval, or human_assistance. Do not use none for runtime_precondition.",
                "Set replay_step_count=-1 when the workflow covers all executable browser actions, even when runtime preconditions or completion verification remain.",
                "When the current task needs replay_action items or inputs absent from the selected workflow, return the number of leading cached steps that are safe to replay before exploration must take over. Exclude any final save, submit, publish, delete, send, or confirmation action that must wait for missing input.",
                "List the uncovered current-task inputs in missing_input_roles. Count steps using their displayed 1-based order, but return a count: 0 means replay none, 8 means replay steps 1 through 8.",
                "Never list upstream preparation outside browser_goal as a browser requirement.",
            ],
        }
        response = await self._llm.ainvoke_structured(
            [
                Message(
                    role=Role.SYSTEM,
                    content=(
                        "You select reusable browser workflows. When resolved_site is present, candidates "
                        "are restricted to it. When it is empty, infer one destination site from the user's "
                        "product/system wording and candidate site_id values; never combine sites. Candidates "
                        "may require parameter_values to be extracted from the request. Choose by "
                        "business intent, not by unstable planner labels or route health. Classify all "
                        "same-operation candidates; do not lower semantic confidence merely because a "
                        "route is candidate or degraded. Return only the requested schema."
                    ),
                ),
                Message(role=Role.USER, content=json.dumps(payload, ensure_ascii=False)),
            ],
            WorkflowSelectionResponse,
        )
        selected_id = str(response.selected_workflow_id or "").strip()
        confidence = float(response.confidence or 0.0)
        matching_ids = _valid_unique_ids(
            [selected_id, *response.matching_workflow_ids],
            valid_ids=set(by_id),
        )
        matching_workflows = tuple(by_id[item] for item in matching_ids)
        if not matching_workflows:
            reason = str(response.reason or "").strip()[:300]
            logger.info(
                "browser workflow semantic selector returned no match: %s",
                reason or "model returned no valid workflow IDs",
                extra={
                    "event": "browser.workflow_cache_semantic_selector_no_match",
                    "site_id": resolved_site,
                    "candidate_count": len(candidates),
                    "selected_workflow_id": selected_id,
                    "confidence": confidence,
                    "reason": reason,
                },
            )
            return None
        workflow = by_id.get(selected_id) or matching_workflows[0]
        return SemanticWorkflowSelection(
            workflow=workflow,
            confidence=confidence,
            reason=str(response.reason or "").strip(),
            matching_workflows=matching_workflows,
            parameter_values=tuple(response.parameter_values),
            replay_step_count=int(response.replay_step_count),
            missing_input_roles=tuple(_normalized_roles(response.missing_input_roles)),
            browser_requirements=tuple(response.browser_requirements),
        )


def _valid_unique_ids(values: Sequence[str], *, valid_ids: set[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        workflow_id = str(value or "").strip()
        if not workflow_id or workflow_id in seen or workflow_id not in valid_ids:
            continue
        seen.add(workflow_id)
        result.append(workflow_id)
    return result


def _input_roles(context: BrowserInputContext) -> list[str]:
    return sorted({
        str(item.semantic_name or item.value_kind or "input").strip().casefold()
        for item in context.candidates
        if str(item.semantic_name or item.value_kind or "").strip()
    })


def _normalized_roles(values: Sequence[str]) -> list[str]:
    return sorted({
        str(item or "").strip().casefold()
        for item in values
        if str(item or "").strip()
    })


def _workflow_summary(workflow: CachedBrowserWorkflow) -> dict:
    completion_capability = str(
        workflow.completion.capability_id if workflow.completion is not None else ""
    ).strip()
    return {
        "workflow_id": workflow.workflow_id,
        "display_name": str(workflow.display_name or "")[:120],
        "site_id": workflow.identity.site_id,
        "operation_hint": workflow.identity.operation_id,
        "capability_hint": workflow.identity.capability_id,
        "completion_hint": completion_capability,
        "input_roles": list(workflow.dynamic_input_roles),
        "request_pattern": _request_pattern(workflow),
        "steps": [
            _step_summary(index, step)
            for index, step in enumerate(workflow.steps[:24], 1)
        ],
        "status": workflow.status,
        "quality_score": int(workflow.quality_score or 0),
        "successful_replays": int(workflow.replay_success_count or 0),
        "consecutive_failures": int(workflow.consecutive_failures or 0),
    }


def _request_pattern(workflow: CachedBrowserWorkflow) -> str:
    template = workflow.request_template
    if template is None or not template.parts:
        return ""
    fragments: list[str] = []
    for index, part in enumerate(template.parts):
        fragments.append(str(part or "")[:160])
        if index < template.slot_count:
            fragments.append("<input>")
    return "".join(fragments)[:600]


def _step_summary(index: int, step: CachedWorkflowStep) -> dict:
    locator = dict(step.locator or {})
    input_bindings = {
        key: binding.semantic_name
        for key, binding in {**step.arg_bindings, **step.locator_bindings}.items()
        if str(binding.semantic_name or "").strip()
    }
    control_role = infer_control_semantic(
        locator, action=str(step.tool or ""), fallback_index=index - 1,
    )
    return {
        "index": index,
        "tool": str(step.tool or ""),
        "target": {
            key: str(locator.get(key) or "")[:120]
            for key in ("role", "name", "text", "placeholder", "semanticPurpose")
            if str(locator.get(key) or "").strip()
        },
        "argument_names": sorted({*step.args.keys(), *step.arg_bindings.keys()}),
        "input_bindings": input_bindings,
        "inferred_control_role": (
            "" if control_role.startswith("field_") else control_role
        ),
        "source_url_shape": str(step.source_url_shape or "")[:160],
        "target_url_shape": str(step.target_url_shape or "")[:160],
        "execution_kind": step.execution_kind,
        "precondition_category": step.precondition_category,
    }


__all__ = [
    "BrowserWorkflowRequirement",
    "SemanticWorkflowSelection",
    "WorkflowSelectionResponse",
    "WorkflowSemanticSelector",
]
