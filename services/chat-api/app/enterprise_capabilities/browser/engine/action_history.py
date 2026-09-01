"""Cross-run history for confirmed browser side effects.

The history stores facts in the existing runtime action-receipt collection.
It does not classify websites or task names.  A model resolves whether the
current operation needs a durable replay guard; local code validates and
enforces the resulting structured policy.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.llm.factory import get_request_scoped_llm_client
from app.llm.types import Message, Role
from app.llm.decision_turn import DecisionOutput, DecisionTurnSpec, invoke_structured_decision
from app.enterprise_capabilities.browser.engine.effect_verification.contracts import EffectContract, EffectReceipt
from app.enterprise_capabilities.browser.engine.business_action import browser_target_identity
from app.governance.action_receipt import ActionReceipt
from app.governance.action_receipt_store import ActionReceiptStore
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


ScopeDimension = Literal["actor", "system", "target", "operation", "purpose", "payload"]


class ReplayPolicy(DecisionOutput):
    guard_across_runs: bool = False
    scope_dimensions: List[ScopeDimension] = Field(default_factory=list)
    max_confirmed: int = 1
    expires_after_seconds: Optional[int] = None
    purpose: str = ""
    confidence: float = 0.0
    reason: str = ""


class _ResolvedReplayPolicy(ReplayPolicy):
    pass


@dataclass(frozen=True)
class ActionHistoryIntent:
    actor_id: str
    system_id: str
    target_id: str
    operation_id: str
    purpose: str
    payload_id: str
    business_key: str
    policy: ReplayPolicy
    attempt_id: str


@dataclass(frozen=True)
class ActionHistoryPreflight:
    blocked: bool
    intent: ActionHistoryIntent
    prior_receipt: Optional[ActionReceipt] = None
    reason: str = ""


class BrowserActionHistory:
    """Resolve and enforce cross-run replay semantics for browser commits."""

    def __init__(
        self,
        *,
        actor_id: str,
        attempt_id: str,
        store: ActionReceiptStore,
        goal: str,
        original_request: str,
        lang: str,
        llm: Any = None,
    ) -> None:
        self.actor_id = str(actor_id or "anonymous").strip() or "anonymous"
        self.attempt_id = str(attempt_id or uuid.uuid4().hex).strip()
        self.store = store
        self.goal = str(goal or "")
        self.original_request = str(original_request or "")
        self.lang = lang
        self.llm = llm
        self._policies: Dict[str, ReplayPolicy] = {}
        self._intents: Dict[str, ActionHistoryIntent] = {}

    async def preflight(
        self,
        *,
        contract: EffectContract,
        observation: Observation,
    ) -> ActionHistoryPreflight:
        operation_id = _operation_identity(contract)
        policy_key = _policy_cache_key(contract)
        policy = self._policies.get(policy_key)
        if policy is None:
            policy = await self._resolve_policy(contract=contract, observation=observation)
            self._policies[policy_key] = policy

        system_id, observed_target_id = target_identity(observation)
        target_id = str(contract.business_target_id or observed_target_id or "")
        payload_id = _payload_identity(contract)
        purpose = str(policy.purpose or contract.intended_entity or contract.entity or operation_id).strip()[:240]
        business_key = _business_key(
            policy=policy,
            actor_id=self.actor_id,
            system_id=system_id,
            target_id=target_id,
            operation_id=operation_id,
            purpose=purpose,
            payload_id=payload_id,
        )
        intent = ActionHistoryIntent(
            actor_id=self.actor_id,
            system_id=system_id,
            target_id=target_id,
            operation_id=operation_id,
            purpose=purpose,
            payload_id=payload_id,
            business_key=business_key,
            policy=policy,
            attempt_id=self.attempt_id,
        )
        self._intents[contract.key()] = intent

        if not policy.guard_across_runs or not business_key:
            return ActionHistoryPreflight(blocked=False, intent=intent)
        prior = await self.store.find_succeeded_by_business_key(business_key)
        if prior is None or _receipt_expired(prior, policy):
            return ActionHistoryPreflight(blocked=False, intent=intent)
        if policy.max_confirmed > 1:
            confirmed_count = await self.store.count_succeeded_by_business_key(business_key)
            if confirmed_count < policy.max_confirmed:
                return ActionHistoryPreflight(blocked=False, intent=intent)
        reason = (
            "相同身份已对当前业务目标完成过相同目的的操作，已跳过本次重复提交。"
            if str(self.lang).startswith("zh") else
            "The same actor already completed this purpose on the current target; duplicate commit skipped."
        )
        return ActionHistoryPreflight(blocked=True, intent=intent, prior_receipt=prior, reason=reason)

    async def record(self, receipt: EffectReceipt, observation: Observation) -> Optional[ActionReceipt]:
        if receipt.status != "confirmed_success":
            return None
        intent = self._intents.get(receipt.contract_key)
        if intent is None:
            return None
        payload = receipt.model_dump(mode="json")
        receipt_seed = "\x00".join([
            intent.attempt_id,
            str(receipt.business_action_id or receipt.contract_key),
            intent.target_id,
            intent.operation_id,
        ])
        stable_id = hashlib.sha256(receipt_seed.encode("utf-8")).hexdigest()
        row = ActionReceipt(
            action_id=f"browser_effect_{stable_id[:24]}",
            idempotency_key=f"browser_effect:{stable_id}",
            status="succeeded",
            result_ref={"effect_receipt": payload},
            evidence={
                "url": str(observation.url or ""),
                "title": str(observation.title or "")[:300],
                "effect_evidence": payload.get("evidence") or [],
            },
            business_key=intent.business_key,
            actor_id=intent.actor_id,
            system_id=intent.system_id,
            target_id=intent.target_id,
            operation_id=intent.operation_id,
            purpose=intent.purpose,
            replay_policy=intent.policy.model_dump(mode="json"),
        )
        return await self.store.upsert(row)

    async def _resolve_policy(
        self,
        *,
        contract: EffectContract,
        observation: Observation,
    ) -> ReplayPolicy:
        client = self.llm or get_request_scoped_llm_client(
            streaming=False,
            intent="browser_automation",
            stage="browser_replay_policy",
        )
        system = (
            "判断当前浏览器副作用在未来独立任务中是否允许再次执行。不要按网站或任务名称套规则。"
            "只根据用户原始请求、节点目标、当前业务对象和操作目的生成结构化策略。"
            "同一次执行的重放由其他机制处理；guard_across_runs 只表示未来任务是否应被历史成功记录阻止。"
            "需要长期避免重复时，系统会自动加入 actor/system/target/operation 基础隔离维度；"
            "你只需判断是否还要增加 purpose 或 payload；"
            "未来任务应正常重复、或每次会创建新业务对象时，guard_across_runs=false。"
            "目标不稳定或证据不足时必须返回 false。不得编造页面没有提供的身份或业务 ID。"
        ) if str(self.lang).startswith("zh") else (
            "Decide whether this browser side effect should be blocked by a successful receipt in a future independent run. "
            "Do not classify by website or task name. Use only the original request, node goal, current business target, and purpose. "
            "Return guard_across_runs=false when future runs may repeat, each run creates a new target, or target identity is uncertain."
        )
        payload = {
            "original_request": self.original_request[:3000],
            "node_goal": self.goal[:3000],
            "operation": {
                "action_name": contract.action_name,
                "operation_family": contract.operation_family,
                "entity": contract.entity,
                "intended_operation": contract.intended_operation,
                "intended_entity": contract.intended_entity,
                "target_operation": contract.target_operation,
                "target_entity": contract.target_entity,
                "fingerprint": contract.fingerprint,
            },
            "page": {
                "url": str(observation.url or "")[:1200],
                "title": str(observation.title or "")[:300],
            },
        }
        try:
            resolved = await invoke_structured_decision(
                client,
                _ResolvedReplayPolicy,
                [
                    Message(role=Role.SYSTEM, content=system),
                    Message(role=Role.USER, content=json.dumps(payload, ensure_ascii=False)),
                ],
                spec=DecisionTurnSpec(locale=self.lang, turn_id="browser.replay_policy"),
            )
        except Exception:
            return ReplayPolicy(reason="replay policy model unavailable")
        policy = ReplayPolicy.model_validate(resolved.model_dump(mode="json"))
        requested_dimensions = list(dict.fromkeys(policy.scope_dimensions))
        confidence = max(0.0, min(1.0, float(policy.confidence)))
        enforce = bool(policy.guard_across_runs and confidence >= 0.72)
        # A durable target is mandatory for cross-run blocking.  Without it,
        # a broad site-level key could suppress unrelated future operations.
        if "target" not in requested_dimensions:
            enforce = False
        dimensions = requested_dimensions
        if enforce:
            mandatory = ["actor", "system", "target", "operation"]
            optional = [item for item in requested_dimensions if item not in mandatory]
            dimensions = mandatory + optional
        return policy.model_copy(update={
            "guard_across_runs": enforce,
            "scope_dimensions": dimensions,
            "max_confirmed": max(1, int(policy.max_confirmed or 1)),
            "expires_after_seconds": (
                max(1, int(policy.expires_after_seconds))
                if policy.expires_after_seconds is not None else None
            ),
            "confidence": confidence,
        })


def target_identity(observation: Observation) -> tuple[str, str]:
    """Return a conservative, site-agnostic system and target identity."""
    return browser_target_identity(observation.url)


def _operation_identity(contract: EffectContract) -> str:
    return str(
        contract.intended_operation
        or contract.target_operation
        or contract.operation_family
        or contract.action_name
        or "custom"
    ).strip().lower()[:160]


def _payload_identity(contract: EffectContract) -> str:
    raw = json.dumps(contract.fingerprint or {}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest() if raw != "{}" else ""


def _business_key(
    *,
    policy: ReplayPolicy,
    actor_id: str,
    system_id: str,
    target_id: str,
    operation_id: str,
    purpose: str,
    payload_id: str,
) -> str:
    if not policy.guard_across_runs:
        return ""
    values = {
        "actor": actor_id,
        "system": system_id,
        "target": target_id,
        "operation": operation_id,
        "purpose": purpose,
        "payload": payload_id,
    }
    selected = {name: values.get(name, "") for name in policy.scope_dimensions}
    if not selected.get("target") or any(not str(value).strip() for value in selected.values()):
        return ""
    raw = json.dumps(selected, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _policy_cache_key(contract: EffectContract) -> str:
    return "\x00".join([
        _operation_identity(contract),
        str(contract.intended_entity or contract.entity or "").strip().lower(),
    ])


def _receipt_expired(receipt: ActionReceipt, policy: ReplayPolicy) -> bool:
    ttl = policy.expires_after_seconds
    if ttl is None:
        return False
    return receipt.updated_at + timedelta(seconds=ttl) < datetime.utcnow()


__all__ = [
    "ActionHistoryIntent",
    "ActionHistoryPreflight",
    "BrowserActionHistory",
    "ReplayPolicy",
    "target_identity",
]
