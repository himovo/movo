"""Stable identity and lifecycle for one browser business mutation.

DOM refs identify controls, not business operations. This module binds the
existing effect contract to the target resource and intended operation so a
SPA re-render cannot turn one publish/send/submit into a second operation.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.enterprise_capabilities.browser.engine.effect_verification.contracts import EffectContract, EffectReceipt
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


@dataclass(frozen=True)
class BusinessActionIdentity:
    business_action_id: str
    action_attempt_id: str
    system_id: str
    target_id: str
    operation_id: str
    entity_id: str
    payload_id: str


@dataclass
class BusinessActionRecord:
    identity: BusinessActionIdentity
    status: str = "prepared"
    contract_key: str = ""
    attempts: int = 0


class BusinessActionLedger:
    """Attempt-local replay guard shared by effects and mission completion."""

    def __init__(self) -> None:
        self._records: Dict[str, BusinessActionRecord] = {}

    def bind_contract(
        self,
        contract: EffectContract,
        observation: Observation,
        *,
        target_hint: str = "",
    ) -> EffectContract:
        identity = identify_business_action(
            contract,
            observation,
            target_hint=target_hint,
        )
        existing = self._records.get(identity.business_action_id)
        if existing is None:
            existing = BusinessActionRecord(identity=identity)
            self._records[identity.business_action_id] = existing
        existing.contract_key = contract.key()
        existing.attempts += 1
        return contract.model_copy(update={
            "business_action_id": identity.business_action_id,
            "action_attempt_id": identity.action_attempt_id,
            "business_target_id": identity.target_id,
            "observation_revision": str(observation.revision or ""),
        })

    def replay_blocker(self, contract: EffectContract) -> Optional[BusinessActionRecord]:
        action_id = str(contract.business_action_id or "")
        record = self._records.get(action_id)
        if record and record.status in {
            "confirmed_success", "confirmed_failure", "pending", "unknown",
        }:
            return record
        return None

    def record(self, receipt: EffectReceipt) -> None:
        action_id = str(receipt.business_action_id or "")
        if not action_id:
            return
        record = self._records.get(action_id)
        if record is None:
            identity = BusinessActionIdentity(
                business_action_id=action_id,
                action_attempt_id=str(receipt.action_attempt_id or ""),
                system_id="",
                target_id=str(receipt.business_target_id or ""),
                operation_id=_operation_identity_from_receipt(receipt),
                entity_id=_entity_identity_from_receipt(receipt),
                payload_id="",
            )
            record = BusinessActionRecord(identity=identity)
            self._records[action_id] = record
        record.status = str(receipt.status or "unknown")
        record.contract_key = str(receipt.contract_key or record.contract_key)

    def export_state(self) -> Dict[str, Any]:
        return {
            "version": 1,
            "records": [
                {
                    "identity": record.identity.__dict__,
                    "status": record.status,
                    "contract_key": record.contract_key,
                    "attempts": record.attempts,
                }
                for record in self._records.values()
            ],
        }

    def restore_state(self, payload: Dict[str, Any]) -> None:
        self._records = {}
        for item in list((payload or {}).get("records") or []):
            if not isinstance(item, dict) or not isinstance(item.get("identity"), dict):
                continue
            try:
                identity = BusinessActionIdentity(**item["identity"])
            except (TypeError, ValueError):
                continue
            self._records[identity.business_action_id] = BusinessActionRecord(
                identity=identity,
                status=str(item.get("status") or "prepared"),
                contract_key=str(item.get("contract_key") or ""),
                attempts=max(0, int(item.get("attempts") or 0)),
            )


def identify_business_action(
    contract: EffectContract,
    observation: Observation,
    *,
    target_hint: str = "",
) -> BusinessActionIdentity:
    system_id, url_target = browser_target_identity(observation.url)
    target_id = str(target_hint or url_target or observation.state_fingerprint or "").strip()
    operation_id = _operation_identity(contract)
    entity_id = _entity_identity(contract)
    payload_id = _payload_identity(contract)
    resource_payload = {
        "system": system_id,
        "target": target_id,
        "operation": operation_id,
        "entity": entity_id,
    }
    business_action_id = _hash(resource_payload)
    action_attempt_id = _hash({**resource_payload, "payload": payload_id})
    return BusinessActionIdentity(
        business_action_id=business_action_id,
        action_attempt_id=action_attempt_id,
        system_id=system_id,
        target_id=target_id,
        operation_id=operation_id,
        entity_id=entity_id,
        payload_id=payload_id,
    )


def browser_target_identity(raw_url: str) -> tuple[str, str]:
    """Return a conservative site and resource identity without auth noise."""
    try:
        parts = urlsplit(str(raw_url or "").strip())
    except Exception:
        return "", ""
    host = str(parts.hostname or "").lower().strip()
    if not host:
        return "", ""
    authority_host = f"[{host}]" if ":" in host else host
    try:
        port = parts.port
    except ValueError:
        return "", ""
    system_id = f"{authority_host}:{port}" if port is not None else authority_host
    path = "/" + "/".join(segment for segment in parts.path.split("/") if segment)
    query = _stable_query(parts.query)
    fragment = str(parts.fragment or "").strip()
    stable_fragment = ""
    if fragment.startswith("/") and fragment != "/":
        fragment_path, _, fragment_query = fragment.partition("?")
        stable_fragment = fragment_path
        stable_fragment_query = _stable_query(fragment_query)
        if stable_fragment_query:
            stable_fragment = f"{stable_fragment}?{stable_fragment_query}"
    canonical = urlunsplit(
        (parts.scheme.lower() or "https", system_id, path or "/", query, stable_fragment),
    )
    target = canonical if path not in {"", "/"} or query or stable_fragment else ""
    return system_id, target


def _stable_query(raw_query: str) -> str:
    volatile = {
        "spm", "timestamp", "ts", "nonce", "signature", "sign", "sid",
        "session", "sessionid", "source", "ref", "from", "tracking",
    }
    pairs = []
    for key, value in parse_qsl(str(raw_query or ""), keep_blank_values=True):
        normalized = key.strip().lower()
        if (
            not normalized
            or normalized.startswith("utm_")
            or normalized in volatile
            or "token" in normalized
            or normalized.endswith("_token")
        ):
            continue
        pairs.append((key, value))
    return urlencode(sorted(pairs), doseq=True)


def _operation_identity(contract: EffectContract) -> str:
    return _normalize(
        contract.intended_operation
        or contract.target_operation
        or contract.operation_family
        or contract.action_name
        or "custom"
    )[:160]


def _entity_identity(contract: EffectContract) -> str:
    return _normalize(
        contract.intended_entity
        or contract.target_entity
        or contract.entity
    )[:240]


def _operation_identity_from_receipt(receipt: EffectReceipt) -> str:
    return _normalize(
        receipt.intended_operation
        or receipt.target_operation
        or receipt.operation_family
        or receipt.action_name
        or "custom"
    )[:160]


def _entity_identity_from_receipt(receipt: EffectReceipt) -> str:
    return _normalize(
        receipt.intended_entity
        or receipt.target_entity
        or receipt.entity
    )[:240]


def _payload_identity(contract: EffectContract) -> str:
    fingerprint = dict(contract.fingerprint or {})
    payload = {
        "confirmed_fill_hashes": fingerprint.get("confirmed_fill_hashes") or [],
        "payload_hash": fingerprint.get("payload_hash") or "",
    }
    return "" if not any(payload.values()) else _hash(payload)


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _hash(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


__all__ = [
    "BusinessActionIdentity",
    "BusinessActionLedger",
    "BusinessActionRecord",
    "browser_target_identity",
    "identify_business_action",
]
