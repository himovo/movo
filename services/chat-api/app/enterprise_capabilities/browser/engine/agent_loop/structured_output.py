from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import Field, model_validator

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation
from app.llm.decision_turn import DecisionOutput
from app.enterprise_capabilities.browser.engine.target_history_policy import (
    TargetHistoryDirective,
)

from .action_segments import safe_first_action, split_at_observation_boundary


PlanTool = Literal[
    "browser_fill", "browser_press", "browser_click", "browser_select",
    "browser_scroll", "browser_wait_for", "browser_observe", "browser_read_text",
    "browser_screenshot", "browser_navigate", "browser_tab_new", "browser_back",
    "browser_forward",
]


class PlannedAction(DecisionOutput):
    tool: PlanTool
    args: Dict[str, Any] = Field(default_factory=dict)


class BrowserPlannerOutput(DecisionOutput):
    kind: Literal["actions", "done", "ask_user", "fail"] = "actions"
    actions: List[PlannedAction] = Field(default_factory=list, max_length=6)
    summary: str = Field(default="", max_length=1000)
    data: Dict[str, Any] = Field(default_factory=dict)
    question: str = Field(default="", max_length=1000)
    reason: str = Field(default="", max_length=1000)
    target_history: TargetHistoryDirective = Field(default_factory=TargetHistoryDirective)

    @model_validator(mode="before")
    @classmethod
    def normalize_single_action_shape(cls, value: Any) -> Any:
        """Accept the common singular spelling emitted by JSON-only providers."""
        if not isinstance(value, dict) or value.get("kind") != "action":
            return value
        normalized = dict(value)
        normalized["kind"] = "actions"
        if not normalized.get("actions") and isinstance(normalized.get("action"), dict):
            normalized["actions"] = [normalized["action"]]
        if not normalized.get("actions") and isinstance(normalized.get("tool"), str):
            normalized["actions"] = [{
                "tool": normalized["tool"],
                "args": normalized.get("args") if isinstance(normalized.get("args"), dict) else {},
            }]
        return normalized


def decision_from_output(output: BrowserPlannerOutput, observation: Observation) -> Decision:
    commentary = {
        "target_history": output.target_history.model_dump(mode="json"),
    }
    if output.kind == "done":
        return Decision(
            "browser_done",
            {"summary": output.summary, "data": dict(output.data)},
            output.summary,
            "model",
            commentary,
        )
    if output.kind == "ask_user":
        return Decision(
            "browser_ask_user", {"question": output.question}, output.reason, "model", commentary,
        )
    if output.kind == "fail":
        return Decision(
            "browser_fail",
            {
                "reason": output.reason or "browser planner declared failure",
                "error_code": "planner_declared_failure",
            },
            output.reason,
            "model",
            commentary,
        )
    if not output.actions:
        return Decision(
            "browser_fail",
            {
                "reason": "browser planner returned no actions",
                "error_code": "planner_action_segment_empty",
            },
            output.reason,
            "system",
            commentary,
        )

    actions = [
        {
            "tool": action.tool,
            "args": {
                key: value
                for key, value in dict(action.args).items()
                if not str(key).startswith("__")
            },
        }
        for action in output.actions
    ]
    actions, boundary_reason = split_at_observation_boundary(actions)
    if len(actions) == 1:
        action = actions[0]
        rationale = (
            f"{output.summary}; {boundary_reason}"
            if boundary_reason and output.summary
            else boundary_reason or output.summary
        )
        return Decision(action["tool"], action["args"], rationale, "model", commentary)
    error = validate_safe_segment(actions, observation)
    if error:
        safe_prefix = safe_first_action(actions, observation)
        if safe_prefix is not None:
            return Decision(
                safe_prefix["tool"],
                safe_prefix["args"],
                f"decomposed unproven action segment before re-observation: {error}",
                "system",
                commentary,
            )
        return Decision(
            "browser_fail",
            {
                "reason": f"browser action segment rejected: {error}",
                "error_code": "planner_action_segment_invalid",
            },
            error,
            "system",
            commentary,
        )
    return Decision(
        "browser_execute_plan",
        {
            "revision": observation.revision,
            "actions": actions,
            "max_duration_ms": 30_000,
        },
        output.summary,
        "model",
        commentary,
    )


def validate_safe_segment(actions: List[Dict[str, Any]], observation: Observation) -> str:
    """Defense in depth; the sidecar applies the same policy before execution."""
    elements = {
        str(item.get("ref") or ""): item
        for item in observation.elements
        if isinstance(item, dict) and item.get("ref")
    }
    transitioned = False
    for action in actions:
        tool = str(action.get("tool") or "")
        args = action.get("args") if isinstance(action.get("args"), dict) else {}
        target = elements.get(str(args.get("ref") or ""))
        if tool == "browser_fill":
            if transitioned:
                return "fill_after_transition"
            if not target or not target.get("editable") or not _is_search_target(target):
                return "only_search_fields_may_be_batched"
        elif tool == "browser_press":
            if transitioned:
                return "multiple_transitions"
            if str(args.get("key") or "").lower() not in {"enter", "return"}:
                return "only_search_enter_may_be_batched"
            if not target or not _is_search_target(target):
                return "search_enter_target_missing"
            transitioned = True
        elif tool == "browser_click":
            if transitioned:
                return "multiple_transitions"
            if not target or not _is_safe_click(target):
                return "click_is_not_a_safe_navigation_target"
            transitioned = True
        elif tool in {"browser_select", "browser_scroll"}:
            if transitioned:
                return "multiple_transitions"
            transitioned = True
        elif tool == "browser_wait_for":
            continue
        else:
            return f"tool_not_batchable:{tool}"
    return ""


def _is_search_target(target: Dict[str, Any]) -> bool:
    return bool(
        str(target.get("role") or "").lower() == "searchbox"
        or target.get("searchContext") is True
        or str(target.get("semanticPurpose") or "") == "search"
    )


def _is_safe_click(target: Dict[str, Any]) -> bool:
    purpose = str(target.get("semanticPurpose") or "")
    if purpose in {"send", "submit", "publish", "save", "create", "delete"}:
        return False
    return bool(
        str(target.get("role") or "").lower() in {"link", "tab"}
        or purpose in {"search", "navigation-expand", "navigation-group"}
    )
