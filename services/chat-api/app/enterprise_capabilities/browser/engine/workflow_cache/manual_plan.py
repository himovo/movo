from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable

from app.enterprise_capabilities.browser.engine.form_input.input_context import BrowserInputContext
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityTask
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import StepRecord

from .compiler import CompiledWorkflow, compile_parameterized_workflow
from .coverage import assess_compiled_workflow
from .distiller import dynamic_input_roles
from .learning_trace import WorkflowLearningTrace
from .manual_inputs import infer_capability, recording_candidates
from .manual_events import normalize_manual_events
from .recorded_target_identity import stabilize_recorded_target_identities
from .terminal_semantics import locator_has_terminal_intent


@dataclass(frozen=True)
class ManualRecordingPlan:
    operation: str
    display_name: str
    capability_id: str
    start_url: str
    action_events: list[Dict[str, Any]]
    context: BrowserInputContext
    node: CapabilityTask
    history: list[StepRecord]
    compiled: CompiledWorkflow
    reasons: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not self.reasons and bool(self.compiled.steps)


def build_manual_recording_plan(
    *,
    events: Iterable[Dict[str, Any]],
    operation: str,
    display_name: str = "",
    capability_id: str = "",
    variable_names: Dict[int, str] | None = None,
) -> ManualRecordingPlan:
    recorded = [dict(item) for item in events if isinstance(item, dict)]
    raw_action_events = [
        item for item in recorded
        if str(item.get("type") or "") not in {"", "recording_started", "recording_stopped"}
    ]
    normalized = normalize_manual_events(raw_action_events)
    # Learn from every raw snapshot, including intermediate editor states that
    # compaction intentionally removed, then enrich only the final action set.
    # Keeping raw targets intact during compaction also preserves mirror-field
    # detection for reactive forms.
    action_events = stabilize_recorded_target_identities(
        normalized.events,
        identity_observations=raw_action_events,
    )
    operation = " ".join(str(operation or "").split()).strip()
    start_url = next((
        str(item.get(key) or "").strip()
        for item in action_events
        for key in ("after_url", "before_url", "url")
        if str(item.get(key) or "").strip()
    ), "")
    context = BrowserInputContext(
        original_request=operation,
        candidates=recording_candidates(action_events, variable_names or {}),
    )
    resolved_capability = _reconcile_capability(
        requested=capability_id or infer_capability(operation, action_events),
        events=action_events,
    )
    node = CapabilityTask(
        node_id="manual-recording:preview",
        goal=operation,
        assigned_agent="browser",
        meta={
            "capability_id": resolved_capability,
            "browser_site_scope": start_url,
        },
    )
    trace = WorkflowLearningTrace()
    trace.capture_recorded(action_events, input_context=context)
    distilled = trace.distill(site_id="")
    history = trace.successful_path(site_id="")
    compiled = compile_parameterized_workflow(history, context)
    reasons: list[str] = []
    if not any(str(item.get("type") or "") == "recording_stopped" for item in recorded):
        reasons.append("recording_not_stopped")
    if not action_events:
        reasons.append("recording_has_no_actions")
    if not start_url:
        reasons.append("recording_site_missing")
    if not operation:
        reasons.append("operation_required")
    reasons.extend(str(gap.reason) for gap in distilled.critical_gaps)
    if not compiled.complete:
        reasons.append("recorded_actions_not_replayable")
    if not compiled.steps:
        reasons.append("recording_has_no_replayable_steps")
    coverage = assess_compiled_workflow(
        steps=compiled.steps,
        context=context,
        capability_id=resolved_capability,
        dynamic_roles=dynamic_input_roles(context),
    )
    reasons.extend(coverage.reasons)
    return ManualRecordingPlan(
        operation=operation,
        display_name=str(display_name or operation)[:120],
        capability_id=resolved_capability,
        start_url=start_url,
        action_events=action_events,
        context=context,
        node=node,
        history=history,
        compiled=compiled,
        reasons=tuple(dict.fromkeys(reason for reason in reasons if reason)),
    )


def _reconcile_capability(*, requested: str, events: list[Dict[str, Any]]) -> str:
    requested = str(requested or "").strip().lower()
    terminal_text = " ".join(
        " ".join(str((item.get("target") or {}).get(key) or "") for key in (
            "name", "text", "semanticPurpose", "placeholder",
        ))
        for item in events
        if str(item.get("type") or "") == "click"
        and locator_has_terminal_intent(item.get("target") if isinstance(item.get("target"), dict) else {})
    ).casefold()
    if any(token in terminal_text for token in ("发布", "发表", "publish")):
        return "browser.publish"
    if any(token in terminal_text for token in ("删除", "delete", "remove")):
        return "browser.delete"
    if terminal_text:
        return "browser.submit"
    has_mutation = any(str(item.get("type") or "") in {
        "fill", "select", "upload", "paste_image",
    } for item in events)
    if has_mutation and requested in {"", "browser.navigate", "browser.read", "browser.search"}:
        return "browser.submit"
    return requested or "browser.navigate"


__all__ = ["ManualRecordingPlan", "build_manual_recording_plan"]
