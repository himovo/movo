from __future__ import annotations

import uuid
import logging
from typing import Any, Dict


logger = logging.getLogger(__name__)


def ensure_trace_id(output_spec: Dict[str, Any]) -> str:
    existing = str((output_spec or {}).get("trace_id") or "").strip()
    if existing:
        return existing
    trace_id = f"trace_{uuid.uuid4().hex[:12]}"
    if isinstance(output_spec, dict):
        output_spec["trace_id"] = trace_id
    return trace_id


def log_trace(*, trace_id: str, scope: str, event: str, **payload: Any) -> None:
    try:
        safe_payload = _safe_payload(payload)
        logger.info(
            _render_message(scope=str(scope or ""), event=str(event or ""), payload=safe_payload),
            extra={
                "event": "trace.%s" % str(event or "event"),
                "trace_id": str(trace_id or ""),
                "trace_scope": str(scope or ""),
                **safe_payload,
            },
        )
    except Exception:
        pass


def pipeline_snapshot(context: Any) -> Dict[str, Any]:
    output_spec = dict(getattr(context, "output_spec", {}) or {})
    content_task_spec = dict(getattr(context, "content_task_spec", {}) or {})
    content_schema = dict(getattr(context, "content_schema", {}) or {})
    content_plan = dict(getattr(context, "content_plan", {}) or {})
    argument_pack = dict(getattr(context, "argument_pack", {}) or {})
    visual_semantics = dict(getattr(context, "visual_semantics", {}) or {})
    template_hint = dict(getattr(context, "template_hint", {}) or {})
    return {
        "intent": str(getattr(context, "intent", "") or ""),
        "intent_agent": str(getattr(context, "intent_agent", "") or ""),
        "selected_skill": str((getattr(context, "selected_skill", {}) or {}).get("name") or ""),
        "task_mode": str((getattr(context, "task_contract", {}) or {}).get("selected_mode") or ""),
        "execution_kind": str(content_task_spec.get("execution_kind") or ""),
        "goal": str((content_task_spec.get("goal") or {}).get("goal_type") or ""),
        "medium": str((content_task_spec.get("medium") or {}).get("channel") or ""),
        "schema": str(content_schema.get("schema_name") or (content_task_spec.get("schema") or {}).get("name") or ""),
        "plan_sections": len(list(content_plan.get("sections") or [])),
        "argument_refs": len(list(argument_pack.get("references") or [])),
        "visual_roles": len(list(visual_semantics.get("roles") or [])),
        "template": str(template_hint.get("template_name") or ""),
        "has_execution_stream": bool(getattr(context, "execution_stream", None) is not None),
        "output_formats": list(output_spec.get("formats") or []),
    }


def stage_scope(stage: Any) -> str:
    return "pipeline.%s" % getattr(stage, "__class__", type(stage)).__name__


def _safe_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    safe: Dict[str, Any] = {}
    for key, value in dict(payload or {}).items():
        safe[str(key)] = _normalize_value(value)
    return safe


def _normalize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for idx, (k, v) in enumerate(value.items()):
            if idx >= 24:
                out["..."] = "truncated"
                break
            out[str(k)] = _normalize_value(v)
        return out
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        return [_normalize_value(x) for x in items[:12]] + (["truncated"] if len(items) > 12 else [])
    return str(value)


def _render_message(*, scope: str, event: str, payload: Dict[str, Any]) -> str:
    templates = {
        "pipeline_started": _msg_pipeline_started,
        "stage_started": _msg_stage_started,
        "stage_completed": _msg_stage_completed,
        "stage_failed": _msg_stage_failed,
        "execution_stream_ready": _msg_execution_stream_ready,
        "pipeline_completed_without_stream": _msg_pipeline_completed_without_stream,
        "intent_resolved": _msg_intent_resolved,
        "intent_parse_failed": _msg_intent_parse_failed,
        "intent_fallback_resolved": _msg_intent_fallback_resolved,
        "agent_resolved": _msg_agent_resolved,
        "model_routed": _msg_model_routed,
        "azure_deployment_resolved": _msg_azure_deployment_resolved,
        "graph_started": _msg_graph_started,
        "graph_completed": _msg_graph_completed,
        "graph_failed": _msg_graph_failed,
        "node_started": _msg_node_started,
        "node_succeeded": _msg_node_succeeded,
        "node_failed": _msg_node_failed,
        "node_suspended": _msg_node_suspended,
        "preflight_quality_ready": _msg_preflight_quality_ready,
        "task_satisfaction_evaluated": _msg_task_satisfaction_evaluated,
        "task_repair_planned": _msg_task_repair_planned,
        "content_repair_applied": _msg_content_repair_applied,
        "semantic_write_skill_applied": _msg_semantic_write_skill_applied,
        "delegate_skill_started": _msg_delegate_skill_started,
        "delegate_skill_event": _msg_delegate_skill_event,
        "delegate_skill_failed": _msg_delegate_skill_failed,
        "delegate_skill_completed": _msg_delegate_skill_completed,
        "forced_first_search": _msg_forced_first_search,
        "research_tool_selected": _msg_research_tool_selected,
        "gateway_decision": _msg_gateway_decision,
        "browse_activity_extracted": _msg_browse_activity_extracted,
        "research_bundle_ready": _msg_research_bundle_ready,
        "interactive_browser_started": _msg_interactive_browser_started,
        "llm_refine_failed": _msg_llm_refine_failed,
    }
    fn = templates.get(event)
    if fn is not None:
        return fn(payload)
    return "%s | %s" % (event, _format_pairs(payload))


def _msg_pipeline_started(payload: Dict[str, Any]) -> str:
    return "Pipeline started | stages=%s%s" % (
        payload.get("stage_count", "?"),
        _snapshot_suffix(payload),
    )


def _msg_stage_started(payload: Dict[str, Any]) -> str:
    return "Stage started%s" % _snapshot_suffix(payload)


def _msg_stage_completed(payload: Dict[str, Any]) -> str:
    return "Stage completed%s" % _snapshot_suffix(payload)


def _msg_stage_failed(payload: Dict[str, Any]) -> str:
    return "Stage failed | error_type=%s error=%s%s" % (
        payload.get("error_type", ""),
        payload.get("error", ""),
        _snapshot_suffix(payload),
    )


def _msg_execution_stream_ready(payload: Dict[str, Any]) -> str:
    return "Execution stream ready%s" % _snapshot_suffix(payload)


def _msg_pipeline_completed_without_stream(payload: Dict[str, Any]) -> str:
    return "Pipeline completed without execution stream%s" % _snapshot_suffix(payload)


def _msg_intent_resolved(payload: Dict[str, Any]) -> str:
    return "Intent resolved | intent=%s has_answer=%s" % (
        payload.get("intent", ""),
        payload.get("has_answer", False),
    )


def _msg_intent_parse_failed(payload: Dict[str, Any]) -> str:
    return "Intent parse failed | error_type=%s error=%s" % (
        payload.get("error_type", ""),
        payload.get("error", ""),
    )


def _msg_intent_fallback_resolved(payload: Dict[str, Any]) -> str:
    return "Intent fallback resolved | intent=%s" % payload.get("intent", "")


def _msg_agent_resolved(payload: Dict[str, Any]) -> str:
    return "Agent resolved | intent=%s agent=%s has_router_answer=%s" % (
        payload.get("intent", ""),
        payload.get("agent_id", ""),
        payload.get("has_router_answer", False),
    )


def _msg_model_routed(payload: Dict[str, Any]) -> str:
    return "Model routed | stage=%s intent=%s node=%s model=%s source=%s" % (
        payload.get("stage", ""),
        payload.get("intent", ""),
        payload.get("node_id", ""),
        payload.get("model", ""),
        payload.get("source", ""),
    )


def _msg_azure_deployment_resolved(payload: Dict[str, Any]) -> str:
    return "Azure deployment resolved | route_key=%s deployment=%s" % (
        payload.get("route_key", ""),
        payload.get("deployment", ""),
    )


def _msg_graph_started(payload: Dict[str, Any]) -> str:
    return "Graph started | run_id=%s intent=%s template=%s version=%s nodes=%s" % (
        payload.get("run_id", ""),
        payload.get("intent", ""),
        payload.get("template", ""),
        payload.get("template_version", ""),
        payload.get("node_count", ""),
    )


def _msg_graph_completed(payload: Dict[str, Any]) -> str:
    return "Graph completed | run_id=%s has_answer=%s terminated_early=%s" % (
        payload.get("run_id", ""),
        payload.get("has_answer", False),
        payload.get("terminated_early", False),
    )


def _msg_graph_failed(payload: Dict[str, Any]) -> str:
    return "Graph failed | error_type=%s error=%s" % (
        payload.get("error_type", ""),
        payload.get("error", ""),
    )


def _msg_node_started(payload: Dict[str, Any]) -> str:
    return "Node started | run_id=%s node=%s agent=%s skill=%s goal=%s" % (
        payload.get("run_id", ""),
        payload.get("node_id", ""),
        payload.get("agent", ""),
        payload.get("target_skill", ""),
        _truncate(payload.get("goal", ""), 100),
    )


def _msg_node_succeeded(payload: Dict[str, Any]) -> str:
    return "Node succeeded | run_id=%s node=%s next=%s artifacts=%s" % (
        payload.get("run_id", ""),
        payload.get("node_id", ""),
        payload.get("next_node_hint", ""),
        ",".join(str(x) for x in list(payload.get("artifacts", []) or [])),
    )


def _msg_node_failed(payload: Dict[str, Any]) -> str:
    return "Node failed | run_id=%s node=%s status=%s artifacts=%s" % (
        payload.get("run_id", ""),
        payload.get("node_id", ""),
        payload.get("status", ""),
        ",".join(str(x) for x in list(payload.get("artifacts", []) or [])),
    )


def _msg_node_suspended(payload: Dict[str, Any]) -> str:
    return "Node suspended | run_id=%s node=%s status=%s artifacts=%s" % (
        payload.get("run_id", ""),
        payload.get("node_id", ""),
        payload.get("status", ""),
        ",".join(str(x) for x in list(payload.get("artifacts", []) or [])),
    )


def _msg_preflight_quality_ready(payload: Dict[str, Any]) -> str:
    return "Preflight quality ready | run_id=%s node=%s score=%s has_research=%s chars=%s" % (
        payload.get("run_id", ""),
        payload.get("node_id", ""),
        payload.get("score", ""),
        payload.get("has_research", ""),
        payload.get("write_chars", ""),
    )


def _msg_task_satisfaction_evaluated(payload: Dict[str, Any]) -> str:
    return "Task satisfaction evaluated | ok=%s score=%s findings=%s" % (
        payload.get("ok", False),
        payload.get("overall_score", ""),
        ",".join(str(x) for x in list(payload.get("findings", []) or [])),
    )


def _msg_task_repair_planned(payload: Dict[str, Any]) -> str:
    return "Task repair planned | required=%s steps=%s" % (
        payload.get("required", False),
        payload.get("step_count", 0),
    )


def _msg_content_repair_applied(payload: Dict[str, Any]) -> str:
    return "Content repair applied | repaired_score=%s actions=%s" % (
        payload.get("repaired_score", ""),
        payload.get("action_count", 0),
    )


def _msg_semantic_write_skill_applied(payload: Dict[str, Any]) -> str:
    return "Semantic write skill applied | node=%s skill=%s" % (
        payload.get("node_id", ""),
        payload.get("write_skill", ""),
    )


def _msg_delegate_skill_started(payload: Dict[str, Any]) -> str:
    return "Delegate skill started | node=%s skill=%s" % (
        payload.get("node_id", ""),
        payload.get("skill", ""),
    )


def _msg_delegate_skill_event(payload: Dict[str, Any]) -> str:
    return "Delegate skill event | node=%s skill=%s event=%s" % (
        payload.get("node_id", ""),
        payload.get("skill", ""),
        payload.get("event_type", ""),
    )


def _msg_delegate_skill_failed(payload: Dict[str, Any]) -> str:
    return "Delegate skill failed | node=%s skill=%s error_type=%s error=%s" % (
        payload.get("node_id", ""),
        payload.get("skill", ""),
        payload.get("error_type", ""),
        payload.get("error", ""),
    )


def _msg_delegate_skill_completed(payload: Dict[str, Any]) -> str:
    return "Delegate skill completed | node=%s skill=%s" % (
        payload.get("node_id", ""),
        payload.get("skill", ""),
    )


def _msg_forced_first_search(payload: Dict[str, Any]) -> str:
    return "Forced first search | node=%s tool=%s" % (
        payload.get("node_id", ""),
        payload.get("tool", ""),
    )


def _msg_research_tool_selected(payload: Dict[str, Any]) -> str:
    return "Research tool selected | node=%s tool=%s args=%s" % (
        payload.get("node_id", ""),
        payload.get("tool", ""),
        ",".join(str(x) for x in list(payload.get("arg_keys", []) or [])),
    )


def _msg_gateway_decision(payload: Dict[str, Any]) -> str:
    return "Gateway decision | node=%s tool=%s decision=%s reason=%s" % (
        payload.get("node_id", ""),
        payload.get("tool", ""),
        payload.get("decision", ""),
        payload.get("reason", ""),
    )


def _msg_browse_activity_extracted(payload: Dict[str, Any]) -> str:
    return "Browse activity extracted | node=%s tool=%s urls=%s" % (
        payload.get("node_id", ""),
        payload.get("tool", ""),
        payload.get("url_count", 0),
    )


def _msg_research_bundle_ready(payload: Dict[str, Any]) -> str:
    return "Research bundle ready | node=%s tools=%s evidence=%s" % (
        payload.get("node_id", ""),
        ",".join(str(x) for x in list(payload.get("tools_used", []) or [])),
        payload.get("evidence_count", 0),
    )


def _msg_interactive_browser_started(payload: Dict[str, Any]) -> str:
    return "Interactive browser started | node=%s goal=%s" % (
        payload.get("node_id", ""),
        _truncate(payload.get("goal", ""), 100),
    )


def _msg_llm_refine_failed(payload: Dict[str, Any]) -> str:
    return "LLM query refine failed | error_type=%s error=%s" % (
        payload.get("error_type", ""),
        payload.get("error", ""),
    )


def _snapshot_suffix(payload: Dict[str, Any]) -> str:
    snapshot = payload.get("snapshot")
    if not isinstance(snapshot, dict):
        return ""
    parts = []
    for key in ["intent", "execution_kind", "medium", "schema", "plan_sections", "template"]:
        value = snapshot.get(key)
        if value in (None, "", [], {}):
            continue
        parts.append("%s=%s" % (key, value))
    return " | " + " ".join(parts) if parts else ""


def _format_pairs(payload: Dict[str, Any]) -> str:
    parts = []
    for key, value in payload.items():
        if value in (None, "", [], {}):
            continue
        if isinstance(value, list):
            rendered = ",".join(str(x) for x in value[:6])
        else:
            rendered = str(value)
        parts.append("%s=%s" % (key, _truncate(rendered, 80)))
    return " ".join(parts[:8]) if parts else "no details"


def _truncate(value: Any, limit: int) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."
