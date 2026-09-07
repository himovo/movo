"""Cross-run history for confirmed browser side effects.

The history stores facts in the existing runtime action-receipt collection.
Replay protection is deliberately deterministic and fail-open: DSH owns
business semantics while this layer blocks only exact, durable duplicates.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from app.enterprise_capabilities.browser.engine.effect_verification.contracts import EffectContract, EffectReceipt
from app.enterprise_capabilities.browser.engine.business_action import browser_target_identity
from app.enterprise_capabilities.browser.engine.action_replay_policy import (
    ScopeDimension,
    resolve_deterministic_replay_policy,
)
from app.governance.action_receipt import ActionReceipt
from app.governance.action_receipt_store import ActionReceiptStore
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation
from app.enterprise_capabilities.browser.engine.target_history_policy import normalize_operation
from app.enterprise_capabilities.browser.engine.target_identity import observation_target_aliases


class ReplayPolicy(BaseModel):
    guard_across_runs: bool = False
    scope_dimensions: List[ScopeDimension] = Field(default_factory=list)
    max_confirmed: int = 1
    expires_after_seconds: Optional[int] = None
    purpose: str = ""
    confidence: float = 0.0
    reason: str = ""


@dataclass(frozen=True)
class ActionHistoryIntent:
    actor_id: str
    system_id: str
    target_id: str
    operation_id: str
    purpose: str
    payload_id: str
    target_aliases: Tuple[str, ...]
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
    ) -> None:
        self.actor_id = str(actor_id or "anonymous").strip() or "anonymous"
        self.attempt_id = str(attempt_id or uuid.uuid4().hex).strip()
        self.store = store
        del goal, original_request
        self.lang = lang
        self._policies: Dict[str, ReplayPolicy] = {}
        self._intents: Dict[str, ActionHistoryIntent] = {}

    async def preflight(
        self,
        *,
        contract: EffectContract,
        observation: Observation,
        semantic_operation: str = "",
    ) -> ActionHistoryPreflight:
        operation_id = normalize_operation(semantic_operation) or _operation_identity(contract)
        policy_key = _policy_cache_key(contract, semantic_operation=operation_id)
        policy = self._policies.get(policy_key)
        if policy is None:
            policy = self._resolve_policy(contract=contract, observation=observation)
            self._policies[policy_key] = policy

        system_id, observed_target_id = target_identity(observation)
        target_id = str(contract.business_target_id or observed_target_id or "")
        target_aliases = observation_target_aliases(
            observation,
            target_hint=target_id,
        )
        if target_aliases:
            target_id = target_aliases[0]
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
            target_aliases=target_aliases,
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

    async def record(
        self,
        receipt: EffectReceipt,
        observation: Observation,
        *,
        source_url: str = "",
    ) -> Optional[ActionReceipt]:
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
                **({"source_url": source_url} if source_url else {}),
            },
            business_key=intent.business_key,
            actor_id=intent.actor_id,
            system_id=intent.system_id,
            target_id=intent.target_id,
            target_aliases=list(intent.target_aliases),
            source_url=str(source_url or "").strip(),
            operation_id=intent.operation_id,
            purpose=intent.purpose,
            replay_policy=intent.policy.model_dump(mode="json"),
        )
        return await self.store.upsert(row)

    def _resolve_policy(
        self,
        *,
        contract: EffectContract,
        observation: Observation,
    ) -> ReplayPolicy:
        _system_id, observed_target_id = target_identity(observation)
        target_id = str(contract.business_target_id or observed_target_id or "")
        operation_id = _operation_identity(contract)
        payload_id = _payload_identity(contract)
        resolved = resolve_deterministic_replay_policy(
            contract,
            target_id=target_id,
            operation_id=operation_id,
            payload_id=payload_id,
        )
        return ReplayPolicy(
            guard_across_runs=resolved.guard_across_runs,
            scope_dimensions=list(resolved.scope_dimensions),
            max_confirmed=1,
            purpose=resolved.purpose,
            confidence=1.0 if resolved.guard_across_runs else 0.0,
            reason=resolved.reason,
        )


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
    fingerprint = {
        key: value
        for key, value in dict(contract.fingerprint or {}).items()
        if key not in {
            "interaction_target_id",
            "confirmed_fill_count",
            "commit_precondition",
        }
        and value not in (None, "", [], {})
    }
    raw = json.dumps(fingerprint, ensure_ascii=False, sort_keys=True, default=str)
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


def _policy_cache_key(contract: EffectContract, *, semantic_operation: str = "") -> str:
    return "\x00".join([
        normalize_operation(semantic_operation) or _operation_identity(contract),
        str(contract.intended_entity or contract.entity or "").strip().lower(),
        str(contract.side_effect or ""),
        "payload" if _payload_identity(contract) else "no-payload",
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
