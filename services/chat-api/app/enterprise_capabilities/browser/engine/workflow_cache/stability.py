from __future__ import annotations

import re
from typing import Callable, Iterable

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision

from .contracts import CachedParameterBinding, CachedWorkflowStep
from .replay_evidence import resolved_wait_text


_POPUP_ROLES = {
    "menuitem", "menuitemradio", "menuitemcheckbox", "option", "treeitem",
}
_TERMINAL_TOKENS = (
    "save", "submit", "publish", "delete", "send", "confirm", "complete",
    "create", "update", "apply", "new",
    "保存", "提交", "发布", "删除", "发送", "确认", "完成",
    "创建", "更新", "应用", "新增", "新建",
)
_POSITIONAL_SELECTOR = re.compile(r":nth-(?:child|of-type)\s*\(", re.I)


def add_readiness_barriers(
    steps: Iterable[CachedWorkflowStep],
) -> list[CachedWorkflowStep]:
    """Insert portable waits at asynchronous UI boundaries.

    The rule is structural rather than site-specific: scrolling before an
    interaction, or opening a popup before selecting one of its children, is
    an asynchronous boundary.  A successful exploration trace may have won a
    race once; the cached workflow must explicitly wait for the next semantic
    target before replaying it.
    """

    source = list(steps)
    stabilized: list[CachedWorkflowStep] = []
    for step in source:
        previous = stabilized[-1] if stabilized else None
        if _needs_barrier(previous, step):
            barrier = _readiness_step(step)
            if barrier is not None and not _same_probe(previous, barrier):
                stabilized.append(barrier)
        stabilized.append(step)
    return stabilized


def readiness_probe(
    step: CachedWorkflowStep | None,
    resolve: Callable[[CachedParameterBinding], object | None],
    *,
    timeout_ms: int = 5000,
) -> Decision | None:
    """Build a value-safe wait for a cached step's semantic target."""

    if step is None:
        return None
    text = resolved_wait_text(step, resolve) if step.tool == "browser_wait_for" else ""
    if not text:
        text = _static_probe_text(step)
    if not text:
        for key in ("name", "text", "placeholder"):
            binding = step.locator_bindings.get(key)
            if binding is None:
                continue
            value = resolve(binding)
            if value is not None and str(value).strip():
                text = str(value).strip()
                break
    if not text:
        return None
    return Decision(
        tool="browser_wait_for",
        args={
            "text": text,
            "probe_only": True,
            "timeout": max(
                250,
                int(step.args.get("timeout") or timeout_ms),
            ),
        },
        rationale="[learned_workflow] wait for the next semantic target",
    )


def safe_to_retry(step: CachedWorkflowStep) -> bool:
    """Return whether repeating the action cannot duplicate a business write."""

    if step.tool in {"browser_scroll", "browser_hover", "browser_wait_for"}:
        return True
    if step.tool not in {"browser_click", "browser_press"}:
        return False
    semantic = " ".join(
        str(step.locator.get(key) or "")
        for key in ("name", "text", "description", "semanticPurpose")
    ).casefold()
    if step.tool == "browser_press":
        role = str(step.locator.get("role") or "").casefold()
        return role == "searchbox" or any(
            token in semantic for token in ("search", "query", "搜索", "查询")
        )
    return not any(token in semantic for token in _TERMINAL_TOKENS)


def fragile_selector(locator: dict) -> bool:
    selector = str(locator.get("selector") or "")
    if not selector or not _POSITIONAL_SELECTOR.search(selector):
        return False
    return not bool(
        locator.get("name")
        or locator.get("text")
        or locator.get("placeholder")
        or locator.get("semanticPurpose")
    )


def replay_failure_reason(index: int, step: CachedWorkflowStep) -> str:
    locator = step.locator or {}
    semantic = str(
        locator.get("name")
        or locator.get("text")
        or locator.get("placeholder")
        or locator.get("semanticPurpose")
        or ""
    ).strip()[:120]
    suffix = f" target={semantic}" if semantic else ""
    return f"cached step failed index={index} tool={step.tool}{suffix}"


def _needs_barrier(
    previous: CachedWorkflowStep | None,
    current: CachedWorkflowStep,
) -> bool:
    if previous is None or current.tool == "browser_wait_for":
        return False
    if current.tool not in {
        "browser_click", "browser_hover", "browser_fill", "browser_select",
        "browser_upload_file", "browser_paste_image", "browser_press",
    }:
        return False
    if previous.tool == "browser_scroll":
        return True
    previous_popup = str(previous.locator.get("hasPopup") or "").casefold()
    current_role = str(current.locator.get("role") or "").casefold()
    return bool(previous_popup and current_role in _POPUP_ROLES)


def _readiness_step(step: CachedWorkflowStep) -> CachedWorkflowStep | None:
    text = _static_probe_text(step)
    binding = None
    if not text:
        binding = next((
            step.locator_bindings[key]
            for key in ("name", "text", "placeholder")
            if key in step.locator_bindings
        ), None)
    if not text and binding is None:
        return None
    return CachedWorkflowStep(
        tool="browser_wait_for",
        args={"text": text, "timeout": 5000} if text else {"timeout": 5000},
        arg_bindings={"text": binding} if binding is not None else {},
        source_url_shape=step.source_url_shape,
        target_url_shape=step.source_url_shape,
        expect_state_change=False,
    )


def _static_probe_text(step: CachedWorkflowStep) -> str:
    for key in ("name", "text", "placeholder"):
        value = str(step.locator.get(key) or "").strip()
        if value:
            return value
    return ""


def _same_probe(
    previous: CachedWorkflowStep | None,
    probe: CachedWorkflowStep,
) -> bool:
    return bool(
        previous is not None
        and previous.tool == "browser_wait_for"
        and previous.args == probe.args
        and previous.arg_bindings == probe.arg_bindings
    )


__all__ = [
    "add_readiness_barriers",
    "fragile_selector",
    "readiness_probe",
    "replay_failure_reason",
    "safe_to_retry",
]
