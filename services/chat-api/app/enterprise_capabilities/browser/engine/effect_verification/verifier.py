from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Literal

from pydantic import BaseModel, Field

from app.llm.factory import get_request_scoped_llm_client
from app.llm.types import Message, Role
from app.llm.decision_turn import DecisionOutput, DecisionTurnSpec, invoke_structured_decision
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation

from .contracts import EffectContract, EffectEvidence, EffectReceipt
from .page_status import collect_new_page_status
from .resource_identity import collect_resource_identity_evidence
from .semantic_alignment import assess_outcome_alignment
from .status_semantics import classify_status_text, is_unambiguous_outcome_text
from .structural_outcome import collect_structural_outcome_evidence


class _ModelVerdict(DecisionOutput):
    status: Literal["confirmed_success", "confirmed_failure", "pending", "unknown"]
    confidence: float = 0.0
    evidence_ids: List[str] = Field(default_factory=list)
    reason: str = ""


async def verify_effect(
    *,
    contract: EffectContract,
    before: Observation,
    after: Observation,
    lang: str,
    llm: Any = None,
    supplemental_evidence: List[EffectEvidence] | None = None,
) -> EffectReceipt:
    evidence = [
        *collect_evidence(contract=contract, before=before, after=after),
        *list(supplemental_evidence or []),
    ]
    deterministic = _deterministic_verdict(contract=contract, evidence=evidence)
    if deterministic is not None:
        receipt = _receipt(contract, evidence, **deterministic)
        return await _apply_semantic_outcome_guard(
            receipt=receipt, contract=contract, after=after, lang=lang, llm=llm,
        )
    if not evidence:
        return _receipt(contract, evidence, status="unknown", confidence=0.0, reason="没有观测到可验证的状态变化")
    model = await _model_verdict(contract=contract, evidence=evidence, lang=lang, llm=llm)
    allowed = {item.evidence_id for item in evidence}
    selected = [item for item in evidence if item.evidence_id in allowed.intersection(model.evidence_ids)]
    # A model may interpret evidence, but it cannot manufacture success from
    # no positive state change. This keeps custom actions open-ended without
    # turning the fallback into an ungrounded success oracle.
    has_positive_change = any(
        item.polarity in {"positive", "pending"} and item.kind != "network_response"
        for item in selected
    )
    status = model.status
    confidence = max(0.0, min(1.0, float(model.confidence)))
    if status != "unknown" and not selected:
        status = "unknown"
        confidence = min(confidence, 0.4)
    if status == "confirmed_success" and (not has_positive_change or confidence < 0.72):
        status = "unknown"
        confidence = min(confidence, 0.6)
    receipt = _receipt(contract, selected or evidence, status=status, confidence=confidence, reason=model.reason)
    return await _apply_semantic_outcome_guard(
        receipt=receipt, contract=contract, after=after, lang=lang, llm=llm,
    )


async def _apply_semantic_outcome_guard(
    *, receipt: EffectReceipt, contract: EffectContract, after: Observation, lang: str, llm: Any,
) -> EffectReceipt:
    if receipt.status not in {"confirmed_success", "pending"} or not contract.intended_entity.strip():
        return receipt
    alignment = await assess_outcome_alignment(
        intended_operation=contract.intended_operation or contract.operation_family,
        intended_entity=contract.intended_entity,
        after=after,
        lang=lang,
        llm=llm,
    )
    if not alignment.blocks_action:
        return receipt
    detail = (
        f"预期业务对象“{alignment.intended.entity}”，实际结果表示“{alignment.observed.entity}”："
        f"{alignment.reason}"
    )
    mismatch = _ev("semantic", "semantic_mismatch", detail, "negative", 1.0)
    return receipt.model_copy(update={
        "status": "confirmed_failure",
        "confidence": alignment.confidence,
        "evidence": [*receipt.evidence, mismatch],
        "reason": detail,
    })


def collect_evidence(*, contract: EffectContract, before: Observation, after: Observation) -> List[EffectEvidence]:
    evidence: List[EffectEvidence] = [
        *collect_new_page_status(before, after),
        *collect_structural_outcome_evidence(before, after),
        *collect_resource_identity_evidence(
            contract=contract,
            before_url=before.url,
            after_url=after.url,
        ),
    ]
    before_refs = {_semantic_element_key(item) for item in before.elements if isinstance(item, dict)}
    after_refs = {_semantic_element_key(item) for item in after.elements if isinstance(item, dict)}
    if before.url and after.url and before.url != after.url:
        evidence.append(_ev("route", "route_changed", f"{before.url} -> {after.url}", "positive", 0.35))
    before_editable = sum(1 for item in before.elements if isinstance(item, dict) and item.get("editable"))
    after_editable = sum(1 for item in after.elements if isinstance(item, dict) and item.get("editable"))
    if before_editable >= 2 and after_editable <= max(0, before_editable - 2):
        evidence.append(_ev("form", "form_closed", f"editable fields {before_editable} -> {after_editable}", "positive", 0.3))
    target_label = contract.action_name.strip().lower()
    if target_label and any(target_label in key for key in before_refs) and not any(target_label in key for key in after_refs):
        evidence.append(_ev("target", "commit_target_disappeared", contract.action_name, "positive", 0.2))

    for index, raw in enumerate(list(getattr(after, "effects", None) or [])[:80]):
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("kind") or "")
        text = str(raw.get("text") or "").strip()[:500]
        if kind in {"dom_added", "dom_changed"} and text:
            role = str(raw.get("role") or "").strip().lower()
            status_surface = role in {"alert", "status", "dialog"}
            status_polarity = classify_status_text(text)
            status_sentence = (
                len(text) <= 100
                and status_polarity != "neutral"
                and is_unambiguous_outcome_text(text)
            )
            interpretable = status_surface or status_sentence
            polarity = status_polarity if interpretable else "neutral"
            weight = 0.8 if polarity in {"positive", "negative"} else 0.45 if polarity == "pending" else 0.1
            evidence.append(_ev(f"dom{index}", "transient_dom", text, polarity, weight))
        elif kind == "network_response":
            status = int(raw.get("status") or 0)
            detail = f"HTTP {status} {str(raw.get('resourceType') or '')} {str(raw.get('url') or '')[:300]}"
            polarity = "negative" if status >= 400 else "positive" if 200 <= status < 300 else "neutral"
            evidence.append(_ev(f"net{index}", "network_response", detail, polarity, 0.2 if polarity != "neutral" else 0.05))
        elif kind == "navigation":
            evidence.append(_ev(f"nav{index}", "navigation_event", str(raw.get("url") or "")[:500], "positive", 0.2))
    return evidence[:80]


def _deterministic_verdict(*, contract: EffectContract, evidence: List[EffectEvidence]) -> Dict[str, Any] | None:
    status_kinds = {"transient_dom", "page_status_delta", "page_message_delta"}
    negatives = [item for item in evidence if item.polarity == "negative" and item.kind in status_kinds]
    if negatives:
        return {"status": "confirmed_failure", "confidence": 0.95, "reason": negatives[0].detail}
    explicit_success = [item for item in evidence if item.polarity == "positive" and item.kind in status_kinds and item.weight >= 0.8]
    if explicit_success:
        return {"status": "confirmed_success", "confidence": 0.95, "reason": explicit_success[0].detail}
    kinds = {item.kind for item in evidence if item.polarity in {"positive", "pending"}}
    transitioned = "route_changed" in kinds and "form_closed" in kinds
    durable_payload = "submitted_value_present" in kinds
    durable_new_result = "submitted_value_added_to_result" in kinds
    if "business_object_id_assigned" in kinds:
        return {
            "status": "confirmed_success",
            "confidence": 0.9,
            "reason": "提交后页面获得了新的稳定业务对象标识",
        }
    if durable_new_result:
        return {
            "status": "confirmed_success",
            "confidence": 0.94,
            "reason": "提交值已离开编辑字段，并作为新增内容出现在非编辑结果区",
        }
    if "collection_count_increased" in kinds and "form_closed" in kinds:
        return {
            "status": "confirmed_success",
            "confidence": 0.86,
            "reason": "提交后编辑表单关闭，且结果集合中的项目数量增加",
        }
    if transitioned and durable_payload:
        return {
            "status": "confirmed_success",
            "confidence": 0.9,
            "reason": "提交后页面发生跳转、编辑表单关闭，且结果页面包含本次填写内容",
        }
    if transitioned:
        reason = "提交后页面发生跳转且编辑表单关闭，但尚未核验业务结果中存在本次填写内容"
        if any(item.polarity == "pending" for item in evidence):
            reason += "，同时捕获到处理中提示"
        return {"status": "pending", "confidence": 0.72, "reason": reason}
    if any(item.polarity == "pending" for item in evidence):
        return {"status": "pending", "confidence": 0.7, "reason": "捕获到处理中状态，等待最终结果或执行回查"}
    return None


async def _model_verdict(*, contract: EffectContract, evidence: List[EffectEvidence], lang: str, llm: Any) -> _ModelVerdict:
    client = llm or get_request_scoped_llm_client(
        streaming=False,
        intent="browser_automation",
        stage="browser_effect_verification",
    )
    system = (
        "你只根据给定证据判断一次浏览器业务操作的结果。只能引用 evidence_id 列表中的证据，不得补充页面上没有的事实。"
        "瞬时提示、路由变化、表单关闭、网络响应和业务对象回查可以组合判断；HTTP 200 不能单独证明业务成功。证据不足必须返回 unknown。"
    ) if lang.startswith("zh") else (
        "Judge a browser business operation only from the supplied evidence IDs. Never invent facts. "
        "HTTP 200 alone does not prove business success; return unknown when evidence is insufficient."
    )
    payload = {
        "contract": contract.model_dump(mode="json"),
        "evidence": [item.model_dump(mode="json") for item in evidence],
    }
    try:
        return await invoke_structured_decision(
            client,
            _ModelVerdict,
            [Message(role=Role.SYSTEM, content=system), Message(role=Role.USER, content=json.dumps(payload, ensure_ascii=False))],
            spec=DecisionTurnSpec(locale=lang, turn_id="browser.effect_verification"),
        )
    except Exception:
        return _ModelVerdict(status="unknown", confidence=0.0, reason="模型验证不可用")


def _receipt(contract: EffectContract, evidence: List[EffectEvidence], *, status: str, confidence: float, reason: str) -> EffectReceipt:
    return EffectReceipt(
        contract_key=contract.key(),
        status=status,  # type: ignore[arg-type]
        confidence=confidence,
        action_name=contract.action_name,
        operation_family=contract.operation_family,
        entity=contract.entity,
        side_effect=contract.side_effect,
        completes_goal=contract.completes_goal,
        evidence=evidence,
        fingerprint=contract.fingerprint,
        verification_hints=contract.verification_hints,
        intended_operation=contract.intended_operation,
        intended_entity=contract.intended_entity,
        target_operation=contract.target_operation,
        target_entity=contract.target_entity,
        reason=reason,
        business_action_id=contract.business_action_id,
        action_attempt_id=contract.action_attempt_id,
        business_target_id=contract.business_target_id,
        observation_revision=contract.observation_revision,
    )


def _semantic_element_key(item: Dict[str, Any]) -> str:
    return " ".join(str(item.get(key) or "").strip().lower() for key in ("role", "name", "text", "type"))


def _ev(prefix: str, kind: str, detail: str, polarity: str, weight: float) -> EffectEvidence:
    return EffectEvidence(evidence_id=f"{prefix}:{abs(hash((kind, detail))) % 10_000_000}", kind=kind, detail=detail, polarity=polarity, weight=weight)  # type: ignore[arg-type]
