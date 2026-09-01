from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from app.browser.local_bridge import AgentNotConnected, LocalBridge
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityTask
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityInputs
from app.services.workflow_browser_node import browser_node_target_name


@dataclass(frozen=True)
class SkillFastPathResult:
    status: str
    result: Dict[str, Any]

    @property
    def completed(self) -> bool:
        return self.status == "completed"

    @property
    def needs_model(self) -> bool:
        return self.status == "unknown"

    def artifacts(self, capability_id: str) -> Dict[str, Any]:
        capability = str(capability_id or "").strip().lower()
        observation = self.result.get("observation")
        observed = observation if isinstance(observation, dict) else {}
        url = str(observed.get("url") or "")
        base = {
            "status": "completed",
            "url": url,
            "completed_actions": int(self.result.get("completed_actions") or 0),
            "execution_tier": str(self.result.get("tier") or "skill"),
        }
        if capability in {"browser.submit", "browser.modify", "browser.delete"}:
            return {"confirmation": base}
        if capability in {"browser.publish", "browser.publish_or_submit"}:
            return {"delivery": base, "publish_receipt": base}
        if capability == "browser.navigate":
            return {"final_url": url}
        if capability in {"browser.read", "browser.navigate_and_extract"}:
            return {"result": {**base, "page_text": str(observed.get("pageText") or "")}}
        if capability == "browser.file_transfer":
            return {"file": base}
        return {"browser_result": self.result}


@dataclass(frozen=True)
class SkillFastPathRequest:
    """A validated local workflow dispatch, before any browser work starts."""

    args: Dict[str, Any]
    domain: Optional[str]


def _workflow_step(node: CapabilityTask) -> Dict[str, Any]:
    meta = node.meta if isinstance(node.meta, dict) else {}
    direct = meta.get("workflow_step")
    if isinstance(direct, dict):
        return dict(direct)
    task_step = meta.get("task_ir_step")
    if not isinstance(task_step, dict):
        return {}
    task_meta = task_step.get("meta")
    return dict(task_meta) if isinstance(task_meta, dict) else {}


def _semantic_config(node: CapabilityTask, step: Dict[str, Any]) -> Dict[str, Any]:
    semantic = step.get("semantic_config")
    if isinstance(semantic, dict):
        return dict(semantic)
    meta = node.meta if isinstance(node.meta, dict) else {}
    semantic = meta.get("semantic_config")
    return dict(semantic) if isinstance(semantic, dict) else {}


def _target_url(node: CapabilityTask, semantic: Dict[str, Any]) -> str:
    target = str(semantic.get("targetUrl") or semantic.get("target_url") or "").strip()
    if target:
        return target
    meta = node.meta if isinstance(node.meta, dict) else {}
    site = meta.get("site_context")
    return str((site or {}).get("entry_url") or "").strip() if isinstance(site, dict) else ""


def _is_browser_skill_step(step: Dict[str, Any]) -> bool:
    node_type = str(step.get("node_type") or step.get("type") or "").strip().lower()
    kind = str(step.get("kind_hint") or step.get("capability_id") or "").strip().lower()
    return node_type == "browser_automation" or kind.startswith("browser.")


def prepare_skill_fast_path(
    *,
    node: CapabilityTask,
    inputs: CapabilityInputs,
    goal: str,
) -> Optional[SkillFastPathRequest]:
    step = _workflow_step(node)
    if not step or not _is_browser_skill_step(step):
        return None
    semantic = _semantic_config(node, step)
    target_url = _target_url(node, semantic)
    target_name = browser_node_target_name(semantic)
    domain = urlparse(target_url).hostname or None if target_url else None
    output_spec = inputs.output_spec if isinstance(inputs.output_spec, dict) else {}
    args = {
        "goal": str(step.get("instruction") or goal or "").strip(),
        "target_name": target_name,
        "target_url": target_url,
        "capability": str((node.meta or {}).get("capability_id") or ""),
        "input_data": output_spec.get("graph_artifacts") or {},
    }
    return SkillFastPathRequest(args=args, domain=domain)


async def execute_skill_fast_path(
    *,
    bridge: LocalBridge,
    request: SkillFastPathRequest,
) -> Optional[SkillFastPathResult]:
    try:
        envelope = await bridge.execute(
            "browser_execute_workflow",
            request.args,
            domain=request.domain,
            timeout=120.0,
        )
    except AgentNotConnected:
        return None
    except Exception as exc:
        return SkillFastPathResult(status="unknown", result={"reason": f"fast-path-dispatch: {exc}"})
    if not bool(envelope.get("ok")):
        return SkillFastPathResult(
            status="unknown",
            result={"reason": str(envelope.get("error") or "fast-path-failed")},
        )
    result = envelope.get("result")
    payload = dict(result) if isinstance(result, dict) else {}
    return SkillFastPathResult(status=str(payload.get("status") or "unknown"), result=payload)


async def try_skill_fast_path(
    *,
    bridge: LocalBridge,
    node: CapabilityTask,
    inputs: CapabilityInputs,
    goal: str,
) -> Optional[SkillFastPathResult]:
    """Compatibility wrapper for callers that do not stream lifecycle events."""

    request = prepare_skill_fast_path(node=node, inputs=inputs, goal=goal)
    if request is None:
        return None
    return await execute_skill_fast_path(bridge=bridge, request=request)
