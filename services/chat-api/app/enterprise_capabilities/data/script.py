"""Thin adapter for the existing sandboxed script-plugin implementation."""

from __future__ import annotations

from typing import Any

from app.enterprise_capabilities.runtime.execution_contracts import CapabilityTask
from app.enterprise_capabilities.data.script_engine.executor import ScriptPluginExecutor
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityInputs

from app.enterprise_capabilities.runtime.contracts import CapabilityExecutionContext
from app.enterprise_capabilities.data.script_contract import compile_script_plugin
from app.enterprise_capabilities.data.script_inputs import governed_script_files
from app.enterprise_capabilities.artifacts.delivery_scope import apply_result_delivery_scope
from app.execution_isolation import ExecutionTarget, route_capability
from app.execution_isolation.skill_bundle import selected_skill_bundle
from app.execution_isolation.call_audit import record_rejected_code
from app.execution_isolation.script_backend import container_backend_enabled
from app.execution_isolation.personal_space import bind_script_task


async def run_script(arguments: dict[str, Any], context: CapabilityExecutionContext) -> dict[str, Any]:
    if route_capability("data.run_script@v1") is not ExecutionTarget.TASK_CONTAINER:
        raise RuntimeError("Governed script execution route is unavailable")
    input_data = dict(arguments.get("data") or {})
    files = governed_script_files(arguments, context)
    reserved = {"user_id", "files", "input_artifacts", "graph_artifacts", "personal_conversation_key"}
    if reserved.intersection(input_data):
        raise ValueError("script data uses a reserved MOVO context key")
    # The active turn is the authority for the user's text. DSH supplies code
    # and optional data, but those arguments must not replace the actual
    # message or a Skill invocation prefix with model-reconstructed text.
    user_request = str(context.turn_context.get("user_request") or "")
    source = str(arguments.get("code") or "")
    try:
        compiled = compile_script_plugin(source)
    except (SyntaxError, ValueError) as exc:
        if container_backend_enabled() and context.message_id:
            record_rejected_code(context.message_id, context.action_id, source, str(exc))
        raise
    node = CapabilityTask(
        node_id=f"dsh-script-{context.action_id}", goal="Run governed data-processing script",
        assigned_agent="agent.analysis", expected_artifacts=["plugin_result", "documents", "images"],
        meta={
            "capability_id": "file.run_script_plugin",
            "semantic_config": {"pluginCode": compiled},
        },
    )
    inputs = CapabilityInputs(
        messages=[],
        raw_messages=[{"role": "user", "content": user_request}] if user_request else [],
        intent=node.goal, language="zh",
        output_spec={
            **input_data,
            "user_id": context.user_id,
            "files": files,
            "input_artifacts": {"data": input_data, "files": files},
            "graph_artifacts": {},
        },
    )
    artifacts: dict[str, Any] = {}
    terminal_status = ""
    terminal_error = ""
    bundle = await selected_skill_bundle(
        skill_id=str(context.turn_context.get("selected_skill_id") or ""),
        tenant_id=context.tenant_id, user_id=context.user_id,
    )
    conversation_key = bind_script_task(
        context.message_id, context.tenant_id, context.user_id, context.conversation_id,
    )
    inputs.output_spec["personal_conversation_key"] = conversation_key
    async for event, produced in ScriptPluginExecutor().execute(
        runtime=None, task_id=context.message_id, run_id=context.action_id,
        node=node, inputs=inputs,
        skills={"_movo_selected_skill_bundle": bundle} if bundle else {},
    ):
        if isinstance(produced, dict):
            artifacts.update(produced)
        if event.get("type") == "subagent_done" and isinstance(event.get("content"), dict):
            terminal_status = str(event["content"].get("status") or "")
            terminal_error = str(event["content"].get("error") or "")
    if terminal_status != "succeeded":
        detail = f": {terminal_error}" if terminal_error else ""
        raise RuntimeError(f"script plugin failed: {terminal_status or 'unknown'}{detail}")
    scoped = apply_result_delivery_scope(artifacts, arguments.get("delivery_scope"))
    return {"success": True, **scoped}
