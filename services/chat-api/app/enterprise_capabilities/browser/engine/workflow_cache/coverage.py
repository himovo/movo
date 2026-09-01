from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from app.enterprise_capabilities.browser.engine.form_input.input_context import BrowserInputContext

from .contracts import CachedBrowserWorkflow, CachedWorkflowStep
from .action_policy import stable_locator_required
from .locator_portability import locator_is_portable
from .url_portability import navigation_url_is_portable


_WRITE_CAPABILITIES = {
    "browser.submit", "browser.modify", "browser.delete",
    "browser.publish", "browser.publish_or_submit", "browser.file_transfer",
}
_TERMINAL_TOKENS = (
    "save", "submit", "publish", "confirm", "delete", "complete",
    "send", "apply", "create", "update",
    "保存", "提交", "发布", "确认", "确定", "删除", "完成", "发送",
    "应用", "创建", "更新", "存草稿", "草稿",
)
_MEDIA_ROLE_TOKENS = ("file", "image", "media", "attachment", "visual_asset", "图片", "附件", "文件")
_MEDIA_TOOLS = {"browser_upload_file", "browser_paste_image"}


@dataclass(frozen=True)
class WorkflowCoverage:
    allowed: bool
    reasons: tuple[str, ...] = ()


def assess_compiled_workflow(
    *,
    steps: Sequence[CachedWorkflowStep],
    context: BrowserInputContext,
    capability_id: str,
    dynamic_roles: Iterable[str] = (),
) -> WorkflowCoverage:
    """Reject structurally incomplete success routes without site-specific rules."""
    reasons: list[str] = []
    tools = {str(step.tool or "") for step in steps}
    roles = {str(role).strip().casefold() for role in dynamic_roles}
    requires_media = any(item.value_kind == "file" for item in context.candidates) or any(
        token in role for role in roles for token in _MEDIA_ROLE_TOKENS
    )
    if requires_media and not (tools & _MEDIA_TOOLS):
        reasons.append("required_media_action_missing")
    if _is_write(capability_id) and not any(
        _is_terminal_step(step, capability_id=capability_id) for step in steps
    ):
        reasons.append("terminal_business_action_missing")
    if any(
        step.tool in {"browser_navigate", "browser_tab_new"}
        and not navigation_url_is_portable(str(step.args.get("url") or ""))
        for step in steps
    ):
        reasons.append("temporary_navigation_url_present")
    if any(
        stable_locator_required(step.tool, step.args)
        and not locator_is_portable(step.locator)
        for step in steps
    ):
        reasons.append("unstable_recorded_locator_present")
    return WorkflowCoverage(allowed=not reasons, reasons=tuple(reasons))


def assess_cached_workflow(workflow: CachedBrowserWorkflow) -> WorkflowCoverage:
    capability_id = str(
        (workflow.completion.capability_id if workflow.completion is not None else "")
        or workflow.identity.capability_id
        or ""
    )
    # Stored workflows no longer contain values; roles retain required input shape.
    context = BrowserInputContext(original_request="", candidates=[])
    return assess_compiled_workflow(
        steps=workflow.steps,
        context=context,
        capability_id=capability_id,
        dynamic_roles=workflow.dynamic_input_roles,
    )


def _is_write(capability_id: str) -> bool:
    return str(capability_id or "").strip().casefold() in _WRITE_CAPABILITIES


def _is_terminal_step(step: CachedWorkflowStep, *, capability_id: str) -> bool:
    tool = str(step.tool or "")
    if tool in _MEDIA_TOOLS and str(capability_id or "").casefold() == "browser.file_transfer":
        return True
    if tool == "browser_select" and str(capability_id or "").casefold() == "browser.modify":
        return True
    if tool == "browser_press":
        return str(step.args.get("key") or "").casefold() == "enter"
    if tool not in {"browser_click", "browser_click_at"}:
        return False
    locator = dict(step.locator or {})
    text = " ".join(str(locator.get(key) or "") for key in (
        "name", "text", "description", "semanticPurpose", "placeholder", "scopeName",
    )).casefold()
    return any(token in text for token in _TERMINAL_TOKENS)


__all__ = ["WorkflowCoverage", "assess_cached_workflow", "assess_compiled_workflow"]
