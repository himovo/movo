"""Typed human handoffs for browser form transactions.

The browser executor owns suspension mechanics; this module only describes
what the user may safely do and how their explicit answer maps back to the
transaction.  Keeping these contracts independent prevents site-specific
form recovery rules from accumulating in the executor.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Mapping, Optional

from app.enterprise_capabilities.browser.engine.effect_verification.contracts import EffectReceipt
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


FORM_FILL_CATEGORY = "form_fill"
FORM_MEDIA_CATEGORY = "form_media"
FORM_COMMIT_CATEGORY = "form_commit"
FORM_EFFECT_VERIFY_CATEGORY = "form_effect_verify"
FORM_TASK_COMPLETION_CATEGORY = "form_task_completion"
_OUTCOMES = {
    FORM_FILL_CATEGORY: ("completed", "unable"),
    FORM_MEDIA_CATEGORY: ("completed", "unable"),
    FORM_COMMIT_CATEGORY: ("completed", "unable"),
    FORM_EFFECT_VERIFY_CATEGORY: ("succeeded", "failed", "uncertain"),
    FORM_TASK_COMPLETION_CATEGORY: ("task_completed", "continue_agent", "uncertain"),
}


def build_assistance_contract(
    *,
    kind: str,
    action: str,
    payload: Optional[Mapping[str, Any]] = None,
    replay_policy: str = "reconcile_before_retry",
) -> Dict[str, Any]:
    body = {
        "kind": kind,
        "action": str(action or "").strip(),
        "payload": dict(payload or {}),
        "replay_policy": replay_policy,
        "allowed_outcomes": list(_OUTCOMES.get(kind, ("completed", "unable"))),
    }
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, default=str)
    return {
        "schema_version": "1.0",
        "contract_id": hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20],
        **body,
    }


def build_fill_assistance_decision(
    *,
    decision: Decision,
    before: Observation,
    error: str,
    lang: str,
) -> Decision:
    args = dict(decision.args or {})
    ref = str(args.get("ref") or "")
    target = next((
        item for item in list(before.elements or [])
        if isinstance(item, dict) and str(item.get("ref") or "") == ref
    ), {})
    label = _label(target) or ref or ("当前字段" if lang.startswith("zh") else "the field")
    contract = build_assistance_contract(
        kind=FORM_FILL_CATEGORY,
        action="fill_field",
        payload={
            "field_ref": ref,
            "field_label": label,
            "field_value": str(args.get("value") or ""),
            "error": str(error or "")[:500],
        },
    )
    return Decision(
        tool="browser_ask_user",
        args={
            "category": FORM_FILL_CATEGORY,
            "question": (
                f"自动填写“{label}”多次未成功。请在浏览器中手动填写，完成后继续。"
                if lang.startswith("zh") else
                f"Automatic entry for {label!r} did not complete. Fill it manually, then continue."
            ),
            "handoff": {"contract": contract},
        },
        rationale="bounded form fill recovery exhausted; request explicit human assistance",
    )


def build_commit_assistance_decision(
    *,
    reason: str,
    candidate_refs: tuple[str, ...],
    lang: str,
) -> Decision:
    contract = build_assistance_contract(
        kind=FORM_COMMIT_CATEGORY,
        action="commit_form",
        payload={"reason": reason, "candidate_refs": list(candidate_refs)},
        replay_policy="never_replay_after_human_completed",
    )
    return Decision(
        tool="browser_ask_user",
        args={
            "category": FORM_COMMIT_CATEGORY,
            "question": (
                "表单内容已填写，但自动操作无法可靠确定保存/提交按钮。"
                "请在浏览器中完成保存或提交，然后告诉我结果。"
                if lang.startswith("zh") else
                "The form is filled, but the save/submit action cannot be resolved safely. "
                "Complete it in the browser and report the outcome."
            ),
            "handoff": {"contract": contract},
        },
        rationale="form commit remained unresolved after a fresh observation and planner correction",
    )


def build_effect_verification_decision(receipt: EffectReceipt, *, lang: str) -> Decision:
    contract = build_assistance_contract(
        kind=FORM_EFFECT_VERIFY_CATEGORY,
        action="verify_committed_effect",
        payload={
            "contract_key": receipt.contract_key,
            "action_name": receipt.action_name,
            "entity": receipt.entity,
            "reason": receipt.reason,
        },
        replay_policy="never_replay",
    )
    return Decision(
        tool="browser_ask_user",
        args={
            "category": FORM_EFFECT_VERIFY_CATEGORY,
            "question": (
                "保存/提交动作可能已经执行，但页面反馈不足，系统无法确认结果。"
                "请查看当前页面并选择：操作成功、操作失败或不确定。系统不会重复提交。"
                if lang.startswith("zh") else
                "The save/submit may have happened, but the page did not provide enough evidence. "
                "Report success, failure, or uncertainty; the action will not be replayed."
            ),
            "handoff": {"contract": contract},
        },
        rationale="side effect verification exhausted; ask the human without replaying the commit",
    )


def build_task_completion_confirmation_decision(
    *,
    reason: str,
    evidence: tuple[str, ...],
    lang: str,
) -> Decision:
    contract = build_assistance_contract(
        kind=FORM_TASK_COMPLETION_CATEGORY,
        action="confirm_human_task_completion",
        payload={"reason": reason, "evidence": list(evidence)},
        replay_policy="never_replay_after_human_task_completed",
    )
    return Decision(
        tool="browser_ask_user",
        args={
            "category": FORM_TASK_COMPLETION_CATEGORY,
            "question": (
                "检测到你在人工操作期间可能已经完成保存、提交或发布，但系统没有该动作的自动回执。"
                "请确认：整个任务是否已经由你人工完成？"
                if lang.startswith("zh") else
                "The page suggests that you may have saved, submitted, or published while in control, "
                "but no automatic receipt exists. Did you complete the entire task manually?"
            ),
            "handoff": {"contract": contract},
        },
        rationale="possible human-side commit has no agent receipt; confirm task completion without replay",
    )


def build_form_repair_assistance_decision(
    *,
    reason: str,
    lang: str,
) -> Decision:
    """Let the user finish a blocked form without pretending it is complete."""
    contract = build_assistance_contract(
        kind=FORM_TASK_COMPLETION_CATEGORY,
        action="repair_or_complete_form",
        payload={"reason": str(reason or "")[:500]},
        replay_policy="never_replay_after_human_task_completed",
    )
    return Decision(
        tool="browser_ask_user",
        args={
            "category": FORM_TASK_COMPLETION_CATEGORY,
            "question": (
                "自动操作在当前表单中无法可靠继续。标题、正文和相关图片已展示在协助卡中。"
                "请在浏览器中处理缺失字段、弹窗或保存/提交步骤：若整个任务已经完成，"
                "请选择“整个任务已完成”；若只是推进了一步，请选择“尚未完成，继续 Agent”。"
                if lang.startswith("zh") else
                "Automation cannot safely continue in the current form. The title, body, and related images "
                "are shown in the assistance card. Complete the blocked field, dialog, or save/submit step. "
                "Choose Entire task completed only if the whole task is done; otherwise return control to the Agent."
            ),
            "handoff": {"contract": contract},
        },
        rationale="form recovery exhausted; let the human repair or complete the live form",
    )


def resume_contract(signal: Mapping[str, Any]) -> Dict[str, Any]:
    contract = signal.get("assistance_contract")
    return dict(contract) if isinstance(contract, Mapping) else {}


def resume_outcome(signal: Mapping[str, Any], *, expected_kind: str = "") -> str:
    contract = resume_contract(signal)
    if expected_kind and str(contract.get("kind") or "") != expected_kind:
        return ""
    outcome = str(signal.get("human_outcome") or "").strip().lower()
    allowed = set(contract.get("allowed_outcomes") or _OUTCOMES.get(expected_kind, ()))
    return outcome if outcome in allowed else ""


def manual_effect_receipt(
    *,
    previous: EffectReceipt,
    outcome: str,
    observation: Observation,
) -> EffectReceipt:
    status = {
        "succeeded": "confirmed_success",
        "failed": "confirmed_failure",
        "uncertain": "unknown",
    }.get(outcome, "unknown")
    return previous.model_copy(update={
        "status": status,
        "confidence": 1.0 if status != "unknown" else 0.0,
        "fingerprint": {
            **dict(previous.fingerprint or {}),
            "human_verified": status != "unknown",
            "human_outcome": outcome,
        },
        "reason": f"human reported outcome: {outcome}",
        "observation_revision": observation.revision,
    })


def manual_commit_receipt(
    *,
    contract: Mapping[str, Any],
    observation: Observation,
) -> EffectReceipt:
    contract_id = str(contract.get("contract_id") or "manual_form_commit")
    return EffectReceipt(
        contract_key=f"human:{contract_id}",
        status="confirmed_success",
        confidence=1.0,
        action_name="Human completed form commit",
        operation_family="submit",
        side_effect="write",
        completes_goal=True,
        fingerprint={"human_verified": True, "assistance_contract_id": contract_id},
        reason="human explicitly confirmed the requested save/submit action",
        observation_revision=observation.revision,
    )


def _label(target: Mapping[str, Any]) -> str:
    for key in ("name", "label", "placeholder", "text"):
        value = " ".join(str(target.get(key) or "").split())
        if value:
            return value[:120]
    return ""


__all__ = [
    "FORM_COMMIT_CATEGORY",
    "FORM_EFFECT_VERIFY_CATEGORY",
    "FORM_FILL_CATEGORY",
    "FORM_MEDIA_CATEGORY",
    "FORM_TASK_COMPLETION_CATEGORY",
    "build_assistance_contract",
    "build_commit_assistance_decision",
    "build_effect_verification_decision",
    "build_fill_assistance_decision",
    "build_form_repair_assistance_decision",
    "build_task_completion_confirmation_decision",
    "manual_commit_receipt",
    "manual_effect_receipt",
    "resume_contract",
    "resume_outcome",
]
