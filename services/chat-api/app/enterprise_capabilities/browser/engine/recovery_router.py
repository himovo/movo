"""Terminal-bound recovery routing for the live browser loop.

This module does not retry tools, suspend runs, or build media resources.  It
only decides whether an exhausted browser failure should reuse a typed human
handoff or remain a real terminal error.  Keeping those mechanics in their
existing owners prevents a second recovery system from growing beside the
form, media, authentication, and graph recovery policies.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping, Optional

from app.enterprise_capabilities.browser.engine.form_human_assistance import (
    build_form_repair_assistance_decision,
)
from app.enterprise_capabilities.browser.engine.human_assistance_policy import BrowserHumanAssistance
from app.enterprise_capabilities.browser.engine.recovery_identity import browser_recovery_dedupe_key
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


RecoveryAction = Literal["assist", "hard_fail"]

MODEL_FAILURE = "model_failure"
LOOP_EXHAUSTED = "loop_exhausted"
INTERACTION_BLOCKED = "interaction_blocked"
OUTPUT_CONTRACT_EXHAUSTED = "output_contract_exhausted"
RESUME_RECONCILIATION_UNAVAILABLE = "resume_reconciliation_unavailable"
BROWSER_CONNECTION_LOST = "browser_connection_lost"
INTERNAL_FAILURE = "internal_failure"

_HARD_SAFETY_MARKERS = (
    "safety policy",
    "policy violation",
    "unsafe operation",
    "安全策略拒绝",
    "违反安全策略",
)


@dataclass(frozen=True)
class BrowserRecoveryPlan:
    action: RecoveryAction
    source: str
    reason: str
    decision: Optional[Decision] = None
    assistance: Optional[BrowserHumanAssistance] = None

    @property
    def can_assist(self) -> bool:
        return bool(
            self.action == "assist"
            and self.decision is not None
            and self.decision.tool == "browser_ask_user"
            and self.assistance is not None
        )


def route_browser_recovery(
    *,
    source: str,
    observation: Observation,
    lang: str,
    error: str = "",
    has_form_payload: bool = False,
    effect_statuses: tuple[str, ...] = (),
    prebuilt_assistance: Decision | None = None,
    preserved_handoff: Mapping[str, object] | None = None,
) -> BrowserRecoveryPlan:
    """Route one exhausted browser failure without changing successful paths."""
    normalized_source = str(source or LOOP_EXHAUSTED).strip()
    reason = str(error or "").strip()

    if prebuilt_assistance is not None:
        if prebuilt_assistance.tool != "browser_ask_user":
            return _hard_fail(normalized_source, reason or "invalid prebuilt recovery decision")
        return _assist(
            source=normalized_source,
            observation=observation,
            decision=prebuilt_assistance,
        )

    statuses = {str(item or "").strip().lower() for item in effect_statuses}
    if "confirmed_failure" in statuses:
        return _hard_fail(normalized_source, reason or "business effect explicitly failed")
    if normalized_source == INTERNAL_FAILURE or _is_safety_failure(reason):
        return _hard_fail(normalized_source, reason or "internal or policy failure")

    if normalized_source == RESUME_RECONCILIATION_UNAVAILABLE:
        handoff = dict(preserved_handoff or {})
        contract = handoff.get("contract")
        category = (
            str(contract.get("kind") or "browser_resume")
            if isinstance(contract, Mapping)
            else "browser_resume"
        )
        question = (
            "人工操作后暂时无法读取最新页面。请保持目标页面打开并切换到正确标签页，"
            "确认页面稳定后再交回 Agent；系统不会重复保存或提交。"
            if lang.startswith("zh") else
            "The latest page could not be read after human action. Keep the target page open, "
            "switch to the correct tab, wait for it to stabilize, then return control. The Agent will not replay a save or submit."
        )
        return _assist(
            source=normalized_source,
            observation=observation,
            decision=Decision(
                tool="browser_ask_user",
                args={
                    "category": category,
                    "question": question,
                    **({"handoff": handoff} if handoff else {}),
                },
                rationale="live page unavailable after human form assistance",
            ),
        )

    connection_failure = normalized_source == BROWSER_CONNECTION_LOST or _is_connection_failure(reason)
    if connection_failure:
        question = (
            "浏览器控制连接已经中断。请确认桌面端浏览器 Agent 仍在运行，重新连接后打开或切回目标页面，"
            "然后点击“已完成，继续执行”。"
            if lang.startswith("zh") else
            "The browser control connection was lost. Ensure the desktop browser Agent is running, "
            "reconnect and return to the target page, then choose Done to continue."
        )
        return _assist(
            source=BROWSER_CONNECTION_LOST,
            observation=observation,
            decision=Decision(
                tool="browser_ask_user",
                args={"category": "browser_connection", "question": question},
                rationale="browser connection recovery exhausted",
            ),
        )

    if not _has_live_page(observation):
        return _hard_fail(normalized_source, reason or "no live browser page is available")

    if has_form_payload:
        return _assist(
            source=normalized_source,
            observation=observation,
            decision=build_form_repair_assistance_decision(
                reason=reason or normalized_source,
                lang=lang,
            ),
        )

    if normalized_source == OUTPUT_CONTRACT_EXHAUSTED:
        question = (
            "当前页面缺少完成任务所需的可见信息。请手动展开、切换或进入包含结果的页面，"
            "页面准备好后再交回 Agent。"
            if lang.startswith("zh") else
            "The current page does not expose enough information to complete the task. "
            "Open, expand, or switch to the page containing the result, then return control."
        )
        category = "browser_evidence"
    else:
        question = (
            "Agent 在当前页面无法可靠判断或执行下一步。请处理遮挡弹窗、展开隐藏菜单，"
            "或手动将页面推进到下一步后交回控制。"
            if lang.startswith("zh") else
            "The Agent cannot reliably determine or perform the next step on this page. "
            "Handle any blocking dialog, reveal hidden controls, or move the page forward, then return control."
        )
        category = "browser_interaction"

    return _assist(
        source=normalized_source,
        observation=observation,
        decision=Decision(
            tool="browser_ask_user",
            args={"category": category, "question": question},
            rationale=f"browser terminal recovery routed from {normalized_source}",
        ),
    )


def _assist(
    *,
    source: str,
    observation: Observation,
    decision: Decision,
) -> BrowserRecoveryPlan:
    question = str((decision.args or {}).get("question") or "").strip()
    category = str((decision.args or {}).get("category") or "browser")
    dedupe_key = browser_recovery_dedupe_key(
        observation,
        family=_assistance_family(category),
    )
    return BrowserRecoveryPlan(
        action="assist",
        source=source,
        reason=question,
        decision=decision,
        assistance=BrowserHumanAssistance(
            source=source,
            question=question,
            dedupe_key=dedupe_key,
        ),
    )


def _assistance_family(category: str) -> str:
    normalized = str(category or "browser").strip().lower()
    if normalized.startswith("form_") or normalized == "media_upload":
        return "form"
    if normalized == "browser_connection":
        return "connection"
    return "interaction"


def _hard_fail(source: str, reason: str) -> BrowserRecoveryPlan:
    return BrowserRecoveryPlan(
        action="hard_fail",
        source=source,
        reason=str(reason or source),
    )


def _has_live_page(observation: Observation) -> bool:
    return bool(
        observation.fresh
        and (
            str(observation.url or "").strip()
            or str(observation.title or "").strip()
            or observation.elements
            or str(observation.page_text or "").strip()
        )
    )


def _is_connection_failure(error: str) -> bool:
    text = str(error or "").casefold()
    return any(marker in text for marker in (
        "agent-disconnected",
        "agent not connected",
        "websocket is not connected",
        "connection closed",
        "dispatch-error",
    ))


def _is_safety_failure(error: str) -> bool:
    text = str(error or "").casefold()
    return any(marker in text for marker in _HARD_SAFETY_MARKERS)


__all__ = [
    "BROWSER_CONNECTION_LOST",
    "BrowserRecoveryPlan",
    "INTERNAL_FAILURE",
    "INTERACTION_BLOCKED",
    "LOOP_EXHAUSTED",
    "MODEL_FAILURE",
    "OUTPUT_CONTRACT_EXHAUSTED",
    "RESUME_RECONCILIATION_UNAVAILABLE",
    "route_browser_recovery",
]
