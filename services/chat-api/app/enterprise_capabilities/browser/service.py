"""Thin DSH adapter around the existing tested native-CDP Browser Agent."""

from __future__ import annotations

import asyncio
from typing import Any

from app.browser.registry import agent_registry
from app.enterprise_capabilities.browser.engine.desktop_agent_executor import DesktopAgentBrowserExecutor
from app.enterprise_capabilities.browser.engine.checkpoint import BrowserCheckpointSession
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityTask
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityInputs
from app.enterprise_capabilities.browser.engine.state_store import SubAgentStateStore

from app.enterprise_capabilities.runtime.contracts import CapabilityExecutionContext
from app.enterprise_capabilities.artifacts.references import authorize_nested_artifact_refs
from app.enterprise_capabilities.browser.result_contract import (
    BrowserResultEventAccumulator,
    build_browser_tool_result,
)
from app.enterprise_capabilities.browser.pending_intervention import pending_browser_result
from app.enterprise_capabilities.browser.progress import BrowserTimelineProjector
from app.enterprise_capabilities.browser.session_identity import resolve_browser_session_id
from app.enterprise_capabilities.browser.artifact_guard import reject_internal_artifact_target


_EXPECTED = {
    "read": ["result"], "navigate": ["final_url"], "submit": ["confirmation"],
    "modify": ["confirmation"], "delete": ["confirmation"], "file_transfer": ["file"],
    "publish": ["delivery"],
}
_checkpoint_store = SubAgentStateStore()


async def browser_task(arguments: dict[str, Any], context: CapabilityExecutionContext) -> dict[str, Any]:
    operation = str(arguments.get("operation") or "read")
    objective = str(arguments.get("objective") or "").strip()
    target_name = str(arguments.get("target_name") or "").strip()
    target_url = str(arguments.get("target_url") or "").strip()
    reject_internal_artifact_target(target_url)
    if agent_registry.get(context.user_id) is None:
        raise ConnectionError("MOVO local browser agent is not connected")
    target = " ".join(item for item in (target_name, target_url) if item)
    goal = f"{target}\n{objective}".strip()
    resume = dict(context.turn_context.get("browser_resume") or {})
    if not resume:
        pending = await pending_browser_result(
            user_id=context.user_id,
            conversation_id=context.conversation_id,
        )
        if pending is not None:
            return {"operation": operation, **pending}
    run_id = str(resume.get("run_id") or context.action_id)
    node_id = str(resume.get("node_id") or f"dsh-browser-{run_id}")
    browser_session_id = resolve_browser_session_id(
        conversation_id=context.conversation_id,
        resume=resume,
    )
    node = CapabilityTask(
        node_id=node_id, goal=goal, assigned_agent="agent.browser",
        expected_artifacts=_EXPECTED.get(operation, ["result"]), success_criteria=["effect is verified"],
        meta={"capability_id": f"browser.{operation}", "semantic_config": {"targetName": target_name, "targetUrl": target_url}},
    )
    cancel_event = asyncio.Event()
    inputs = CapabilityInputs(
        messages=[], raw_messages=[{"role": "user", "content": objective}], intent=objective,
        output_spec={
            "user_id": context.user_id, "main_id": context.tenant_id,
            "task_id": context.conversation_id, "session_id": context.conversation_id, "run_id": run_id,
            "resume_node_id": node_id,
            "suspension_id": str(resume.get("suspension_id") or ""),
            "resume_signal": dict(resume.get("resume_signal") or {}),
            "input_artifacts": authorize_nested_artifact_refs(dict(arguments.get("inputs") or {}), user_id=context.user_id),
            # Preserve a full minute for result projection before the
            # Capability Gateway's immutable 300-second hard deadline.
            "execution_budget_seconds": 240,
        },
        language=str(context.turn_context.get("language") or "zh"),
        cancel_event=cancel_event,
    )
    checkpoint_session = BrowserCheckpointSession(
        store=_checkpoint_store, task_id=context.conversation_id, run_id=run_id, node=node,
    )
    await checkpoint_session.open()
    executor = DesktopAgentBrowserExecutor(
        context.user_id, browser_session_id, checkpoint_session=checkpoint_session,
    )
    artifacts: dict[str, Any] = {}
    result_events = BrowserResultEventAccumulator()
    timeline = BrowserTimelineProjector(
        outer_action_id=context.action_id,
        message_id=context.message_id,
        language=str(context.turn_context.get("language") or "zh"),
    )
    try:
        async for event, produced in executor.execute(node=node, inputs=inputs):
            if isinstance(event, dict):
                result_events.record(event)
                for projected in timeline.project(event):
                    await context.publish_progress(projected)
            if isinstance(produced, dict):
                artifacts.update(produced)
    except asyncio.CancelledError:
        cancel_event.set()
        await checkpoint_session.finish("cancelled")
        raise
    terminal = result_events.latest("subagent_done")
    status = str((terminal.get("content") or {}).get("status") or "") if isinstance(terminal.get("content"), dict) else ""
    final_status = status or ("completed" if artifacts else "failed_terminal")
    if final_status not in {"suspended_waiting_approval", "intervention_required"}:
        await checkpoint_session.finish("succeeded" if (final_status in {"succeeded", "completed", "done"} or bool(artifacts)) else "failed_terminal")
    return build_browser_tool_result(
        operation=operation,
        status=final_status,
        artifacts=artifacts,
        events=result_events.events,
        event_counts=result_events.event_counts,
    )
